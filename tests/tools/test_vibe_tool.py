from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from tools.vibe.vibe_tool import VibeTool


@pytest.fixture
def write_config(tmp_path):
    def _write(extra: str = ""):
        config = f"""
app_name: OpenQuantMaster
environment: testing
paths:
  artifacts: {tmp_path / "artifacts"}
vibe_trading:
  mode: cli
  cli_path: vibe-trading
  allowed_capabilities:
    - backtest
    - research
{extra}
"""
        (tmp_path / "config.yaml").write_text(config)

    return _write


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vibe_tool_backtest_cli_success(tmp_path, monkeypatch, write_config):
    monkeypatch.chdir(tmp_path)
    write_config()
    (tmp_path / "artifacts").mkdir()

    run_dir = tmp_path / "vibe_run_abc"
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True)
    (artifacts_dir / "equity.csv").write_text("date,equity\n2026-01-01,10000\n")
    (artifacts_dir / "trades.csv").write_text("id,symbol,side\n1,BTCUSDT,buy\n")
    (artifacts_dir / "metrics.csv").write_text("metric,value\nsharpe,1.5\n")
    run_card = {"sharpe": 1.5, "max_drawdown_pct": -0.05, "total_return_pct": 0.12}
    (artifacts_dir / "run_card.json").write_text(json.dumps(run_card))

    async def fake_subprocess(*cmd, **kwargs):
        assert cmd[0] == "vibe-trading"
        summary = {
            "status": "success",
            "run_id": "abc",
            "run_dir": str(run_dir),
            "reason": None,
        }
        fake_proc = AsyncMock()
        fake_proc.returncode = 0
        fake_proc.communicate.return_value = (
            json.dumps(summary).encode("utf-8"),
            b"",
        )
        return fake_proc

    with patch(
        "runtime.vibe_bridge.asyncio.create_subprocess_exec",
        side_effect=fake_subprocess,
    ):
        tool = VibeTool()
        result = await tool.execute(
            {
                "capability": "backtest",
                "inputs": {
                    "strategy_description": "dual EMA on BTCUSDT",
                    "market": "crypto",
                    "symbols": ["BTCUSDT"],
                    "start": "2026-01-01",
                    "end": "2026-06-30",
                },
            }
        )

    assert result.success is True
    assert result.data["capability"] == "backtest"
    assert result.data["run_dir"] == str(run_dir)
    artifact_names = {a.name for a in result.artifacts}
    assert artifact_names == {"equity.csv", "trades.csv", "metrics.csv", "run_card.json"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vibe_tool_run_dir_deterministic(tmp_path, monkeypatch, write_config):
    monkeypatch.chdir(tmp_path)
    write_config()
    (tmp_path / "artifacts").mkdir()

    run_dir = tmp_path / "existing_run"
    run_dir.mkdir()
    (run_dir / "config.json").write_text(json.dumps({"codes": ["BTCUSDT"]}))
    (run_dir / "code").mkdir()
    (run_dir / "code" / "signal_engine.py").write_text("# signal engine")
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir()
    (artifacts_dir / "equity.csv").write_text("date,equity\n2026-01-01,10000\n")
    (artifacts_dir / "metrics.csv").write_text("metric,value\nsharpe,1.5\n")
    (artifacts_dir / "run_card.json").write_text(
        json.dumps({"sharpe": 1.5, "max_drawdown_pct": -0.05, "total_return_pct": 0.12})
    )

    async def fake_subprocess(*cmd, **kwargs):
        fake_proc = AsyncMock()
        fake_proc.returncode = 0
        fake_proc.communicate.return_value = (b"", b"")
        return fake_proc

    with patch(
        "runtime.vibe_bridge.asyncio.create_subprocess_exec",
        side_effect=fake_subprocess,
    ):
        tool = VibeTool()
        result = await tool.execute(
            {
                "capability": "backtest",
                "inputs": {"run_dir": str(run_dir)},
            }
        )

    assert result.success is True
    assert result.data["run_dir"] == str(run_dir)
    artifact_names = {a.name for a in result.artifacts}
    assert {"equity.csv", "metrics.csv", "run_card.json"} <= artifact_names


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vibe_tool_blocks_unallowed_capability(tmp_path, monkeypatch, write_config):
    monkeypatch.chdir(tmp_path)
    write_config(
        extra="""
  allowed_capabilities:
    - research
"""
    )
    (tmp_path / "artifacts").mkdir()

    tool = VibeTool()
    result = await tool.execute(
        {
            "capability": "backtest",
            "inputs": {"strategy_description": "test"},
        }
    )

    assert result.success is False
    assert "not in allowed_capabilities" in result.error


@pytest.mark.unit
@pytest.mark.asyncio
async def test_vibe_tool_mcp_mode_override(tmp_path, monkeypatch, write_config):
    monkeypatch.chdir(tmp_path)
    write_config()
    (tmp_path / "artifacts").mkdir()

    run_dir = tmp_path / "vibe_run_mcp"
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True)
    (artifacts_dir / "run_card.json").write_text(json.dumps({"sharpe": 1.2}))

    class FakeMcpBridge:
        async def call_tool(self, name, arguments):
            assert name == "run_backtest"
            return {"run_dir": str(run_dir)}

    with patch(
        "runtime.mcp_bridge.McpBridge.get_instance",
        return_value=FakeMcpBridge(),
    ):
        tool = VibeTool()
        result = await tool.execute(
            {
                "capability": "backtest",
                "inputs": {"strategy_description": "test", "symbols": ["BTC"], "market": "crypto"},
                "mode": "mcp",
            }
        )

    assert result.success is True
    assert result.data["mode"] == "mcp"
    assert result.data["run_dir"] == str(run_dir)
