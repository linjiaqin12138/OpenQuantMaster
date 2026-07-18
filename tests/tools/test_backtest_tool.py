import json
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import patch

import pytest
from pydantic import BaseModel

from tools.research.backtest_tool import BacktestInput, BacktestOutput, BacktestTool


@pytest.mark.unit
@pytest.mark.asyncio
async def test_backtest_tool_runs_cli_and_reads_artifacts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(
        """
app_name: OpenQuantMaster
environment: testing
paths:
  artifacts: ./artifacts
vibe_trading:
  mode: cli
  cli_path: vibe-trading
"""
    )

    def fake_run(cmd, *args, **kwargs):
        output_dir = Path(kwargs["cwd"])
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "equity.csv").write_text("date,equity\n2026-01-01,10000\n")
        (output_dir / "trades.csv").write_text("id,symbol,side\n1,BTCUSDT,buy\n")
        (output_dir / "metrics.csv").write_text("metric,value\nsharpe,1.5\n")
        run_card = {"sharpe": 1.5, "max_drawdown_pct": -0.05, "total_return_pct": 0.12}
        (output_dir / "run_card.json").write_text(json.dumps(run_card))
        class Result:
            returncode = 0
            stdout = ""
            stderr = ""
        return Result()

    with patch("subprocess.run", side_effect=fake_run):
        tool = BacktestTool()
        result = await tool.execute(
            {
                "strategy_description": "dual EMA on BTCUSDT",
                "market": "crypto",
                "symbols": ["BTCUSDT"],
                "start": "2026-01-01",
                "end": "2026-06-30",
            }
        )

    assert result.success is True
    assert result.data["sharpe"] == 1.5
    assert result.data["max_drawdown_pct"] == -0.05
    assert len(result.artifacts) == 4
    artifact_names = {a.name for a in result.artifacts}
    assert artifact_names == {"equity.csv", "trades.csv", "metrics.csv", "run_card.json"}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_backtest_tool_reads_existing_run_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text("app_name: OpenQuantMaster\nenvironment: testing\n")

    run_dir = tmp_path / "existing_run"
    run_dir.mkdir()
    (run_dir / "equity.csv").write_text("date,equity\n2026-01-01,10000\n")
    (run_dir / "trades.csv").write_text("id,symbol,side\n1,BTCUSDT,buy\n")
    (run_dir / "metrics.csv").write_text("metric,value\nsharpe,1.5\n")
    (run_dir / "run_card.json").write_text(json.dumps({"sharpe": 1.5, "max_drawdown_pct": -0.05, "total_return_pct": 0.12}))

    tool = BacktestTool()
    result = await tool.execute(
        {
            "run_dir": str(run_dir),
            "market": "crypto",
            "symbols": ["BTCUSDT"],
        }
    )

    assert result.success is True
    assert result.data["sharpe"] == 1.5
