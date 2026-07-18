import json
from pathlib import Path

import pytest

from tools.research.signal_scan_tool import SignalScanTool


@pytest.mark.unit
@pytest.mark.asyncio
async def test_signal_scan_tool_reads_latest_run(tmp_path):
    watch_dir = tmp_path / "vibe_runs"
    run_dir = watch_dir / "dual_ema_v1_20260716_081500"
    run_dir.mkdir(parents=True)
    (run_dir / "run_card.json").write_text(
        json.dumps({"strategy_id": "dual_ema_v1", "market": "crypto"})
    )
    (run_dir / "signals.json").write_text(
        json.dumps(
            [
                {
                    "symbol": "BTCUSDT",
                    "interval": "15m",
                    "side": "long",
                    "strength": 0.85,
                    "generated_at": "2026-07-16T08:15:00Z",
                    "metadata": {"reason": "golden cross"},
                }
            ]
        )
    )

    tool = SignalScanTool()
    result = await tool.execute(
        {"watch_dir": str(watch_dir), "strategy_id": "dual_ema_v1", "market": "crypto"}
    )

    assert result.success is True
    assert len(result.data["signals"]) == 1
    assert result.data["signals"][0]["symbol"] == "BTCUSDT"
    assert result.artifacts[0].name == "signals.json"
    assert "BTCUSDT" in result.artifacts[0].content


@pytest.mark.unit
@pytest.mark.asyncio
async def test_signal_scan_tool_returns_empty_when_no_run(tmp_path):
    tool = SignalScanTool()
    result = await tool.execute(
        {"watch_dir": str(tmp_path), "strategy_id": "missing", "market": "crypto"}
    )
    assert result.success is True
    assert result.data["signals"] == []
