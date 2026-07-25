from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from runtime.config_loader import load_config
from runtime.vibe_bridge import VibeBridge


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(
        """
app_name: OpenQuantMaster
environment: testing
vibe_trading:
  mode: cli
  cli_path: vibe-trading
  allowed_capabilities:
    - backtest
    - research
"""
    )
    cfg = load_config()
    return VibeBridge(cfg)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vibe_bridge_cli_backtest_success(bridge, tmp_path):
    run_dir = tmp_path / "vibe_run_abc"
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True)
    (artifacts_dir / "run_card.json").write_text(json.dumps({"sharpe": 1.5}))

    async def fake_subprocess(*cmd, **kwargs):
        assert cmd[0] == "vibe-trading"
        summary = {"status": "success", "run_dir": str(run_dir)}
        fake_proc = AsyncMock()
        fake_proc.returncode = 0
        fake_proc.communicate.return_value = (
            json.dumps(summary).encode("utf-8"),
            b"",
        )
        return fake_proc

    with patch("runtime.vibe_bridge.asyncio.create_subprocess_exec", side_effect=fake_subprocess):
        result = await bridge.call(
            "backtest",
            {
                "strategy_description": "dual EMA",
                "market": "crypto",
                "symbols": ["BTC"],
            },
        )

    assert result.success is True
    assert result.run_dir == str(run_dir)
    assert any(a.name == "run_card.json" for a in result.artifacts)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vibe_bridge_research_prompt_has_no_empty_on_suffix(bridge, tmp_path):
    captured_cmd = []

    async def fake_subprocess(*cmd, **kwargs):
        captured_cmd.extend(cmd)
        summary = {"status": "success", "run_dir": str(tmp_path / "vibe_run")}
        fake_proc = AsyncMock()
        fake_proc.returncode = 0
        fake_proc.communicate.return_value = (
            json.dumps(summary).encode("utf-8"),
            b"",
        )
        return fake_proc

    with patch("runtime.vibe_bridge.asyncio.create_subprocess_exec", side_effect=fake_subprocess):
        await bridge.call("research", {"prompt": "调研近期国际局势并设计A股策略"})

    prompt = captured_cmd[captured_cmd.index("-p") + 1]
    assert prompt == "调研近期国际局势并设计A股策略"
    assert " on " not in prompt


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vibe_bridge_cli_run_dir_runner(bridge, tmp_path):
    import sys

    run_dir = tmp_path / "existing_run"
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True)
    (artifacts_dir / "equity.csv").write_text("date,equity\n2026-01-01,100\n")

    async def fake_subprocess(*cmd, **kwargs):
        assert cmd[:3] == (sys.executable, "-m", "backtest.runner")
        fake_proc = AsyncMock()
        fake_proc.returncode = 0
        fake_proc.communicate.return_value = (b"", b"")
        return fake_proc

    with patch("runtime.vibe_bridge.asyncio.create_subprocess_exec", side_effect=fake_subprocess):
        result = await bridge.call("backtest", {"run_dir": str(run_dir)})

    assert result.success is True
    assert result.run_dir == str(run_dir)
    assert any(a.name == "equity.csv" for a in result.artifacts)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vibe_bridge_blocks_unallowed_capability(bridge):
    with pytest.raises(Exception) as exc_info:
        await bridge.call("alpha_bench", {"zoo": "gtja191"})
    assert "not in allowed_capabilities" in str(exc_info.value)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vibe_bridge_mcp_mode(bridge, tmp_path):
    bridge._cfg.vibe_trading.mode = "mcp"
    run_dir = tmp_path / "mcp_run"
    (run_dir / "artifacts").mkdir(parents=True)
    (run_dir / "artifacts" / "run_card.json").write_text(json.dumps({"sharpe": 1.2}))

    class FakeMcpBridge:
        async def call_tool(self, name, arguments):
            assert name == "run_backtest"
            return {"run_dir": str(run_dir)}

    with patch("runtime.mcp_bridge.McpBridge.get_instance", return_value=FakeMcpBridge()):
        result = await bridge.call("backtest", {"strategy_description": "test"})

    assert result.success is True
    assert result.run_dir == str(run_dir)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vibe_bridge_http_mode_returns_not_implemented(bridge):
    bridge._cfg.vibe_trading.mode = "http"
    result = await bridge.call("backtest", {})
    assert result.success is False
    assert "not implemented" in result.error.lower()
