import json
from typing import Any, ClassVar
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
import yaml
from pydantic import BaseModel

from runtime.bootstrap import bootstrap
from runtime.state_store.models import MarketType, RunStatus, SignalSide
from tools.base.base_tool import BaseTool
from tools.base.tool_result import ArtifactRef, ToolResult


class FakeOHLCVInput(BaseModel):
    symbol: str
    market: str
    interval: str


class FakeOHLCVOutput(BaseModel):
    symbol: str
    market: str
    interval: str
    rows: int
    artifact: str


class FakeOHLCVTool(BaseTool):
    name: ClassVar[str] = "ohlcv_tool"
    version: ClassVar[str] = "0.1.0"
    capability: ClassVar[str] = "market_data"
    input_model: ClassVar[type[BaseModel]] = FakeOHLCVInput
    output_model: ClassVar[type[BaseModel]] = FakeOHLCVOutput

    async def _execute(self, inputs: dict[str, Any]) -> ToolResult:
        artifact_name = f"ohlcv_{inputs['symbol']}_{inputs['interval']}.csv"
        return ToolResult(
            success=True,
            data={
                "symbol": inputs["symbol"],
                "market": inputs["market"],
                "interval": inputs["interval"],
                "rows": 1,
                "artifact": artifact_name,
            },
            artifacts=[
                ArtifactRef(
                    name=artifact_name,
                    mime_type="text/csv",
                    relative_path=artifact_name,
                    sha256="",
                    content="timestamp,open,high,low,close,volume\n2026-07-16T00:00:00Z,1,2,3,4,5\n",
                )
            ],
        )


@pytest_asyncio.fixture
async def m2_setup(tmp_path, monkeypatch):
    import tools

    monkeypatch.chdir(tmp_path)
    pipelines_dir = tmp_path / "pipelines"
    pipelines_dir.mkdir()
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"""
app_name: OpenQuantMaster
environment: testing
paths:
  artifacts: {tmp_path / "artifacts"}
  logs: {tmp_path / "logs"}
  database: {tmp_path / "data" / "runtime.db"}
scheduler:
  timezone: UTC
event_bus:
  backend: memory
logging:
  level: DEBUG
  format: console
market_data:
  crypto:
    default_exchange: binance
    sandbox: false
    exchange_keys: {{}}
  equities:
    tushare_token: ""
    yfinance_timeout: 30
vibe_trading:
  mode: cli
  cli_path: vibe-trading
  http_url: http://localhost:8000
  mcp_url: stdio
"""
    )
    result = await bootstrap(config_path, package=tools)
    result.config.paths.artifacts = tmp_path / "artifacts"
    result.runner._pipelines_dir = pipelines_dir
    yield result
    await result.store.close()
    await result.bus.stop()
    await result.scheduler.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_crypto_signal_fired_pipeline(m2_setup, tmp_path):
    m2_setup.registry._tools["ohlcv_tool"] = FakeOHLCVTool()

    watch_dir = tmp_path / "vibe_runs"
    run_dir = watch_dir / "dual_ema_v1_20260716_080000"
    run_dir.mkdir(parents=True)
    (run_dir / "run_card.json").write_text(
        json.dumps({"strategy_id": "dual_ema_v1", "market": "crypto"})
    )
    (run_dir / "signals.json").write_text(
        json.dumps(
            [
                {
                    "symbol": "SOLUSDT",
                    "interval": "15m",
                    "side": "long",
                    "strength": 0.85,
                    "generated_at": "2026-07-16T08:00:00Z",
                }
            ]
        )
    )

    pipelines_dir = m2_setup.runner._pipelines_dir
    (pipelines_dir / "crypto_signal_fired.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "crypto_signal_fired",
                "version": "1.0",
                "trigger": {"type": "cron", "cron": "*/15 * * * *", "timezone": "UTC"},
                "stages": [
                    {
                        "name": "fetch_ohlcv",
                        "tool": "ohlcv_tool",
                        "inputs": {
                            "symbol": "SOLUSDT.P",
                            "market": "crypto",
                            "interval": "15m",
                        },
                    },
                    {
                        "name": "scan_signals",
                        "tool": "signal_scan_tool",
                        "inputs": {
                            "strategy_id": "dual_ema_v1",
                            "market": "crypto",
                            "watch_dir": str(watch_dir),
                        },
                    },
                ],
            }
        )
    )

    run_id = await m2_setup.runner.run_pipeline("crypto_signal_fired")
    run = await m2_setup.store.get_pipeline_run(run_id)
    assert run.status == RunStatus.completed

    signals = await m2_setup.store.list_signals("dual_ema_v1")
    assert len(signals) == 1
    assert signals[0].symbol == "SOLUSDT"
    assert signals[0].market == MarketType.crypto
    assert signals[0].side == SignalSide.long

    artifact_names = {a.name for a in run.artifact_refs}
    assert "ohlcv_SOLUSDT.P_15m.csv" in artifact_names
    assert "signals.json" in artifact_names


@pytest.mark.integration
@pytest.mark.asyncio
async def test_backtest_demo_pipeline(m2_setup, tmp_path, monkeypatch):
    run_dir = tmp_path / "vibe_backtest_123"
    run_dir.mkdir()
    (run_dir / "config.json").write_text(json.dumps({"codes": ["SOLUSDT.P"]}))
    (run_dir / "code").mkdir()
    (run_dir / "code" / "signal_engine.py").write_text("# signal engine")
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir()
    (artifacts_dir / "equity.csv").write_text("date,equity\n2026-01-01,10000\n")
    (artifacts_dir / "trades.csv").write_text("id,symbol,side\n1,SOLUSDT.P,buy\n")
    (artifacts_dir / "metrics.csv").write_text("metric,value\nsharpe,1.5\n")
    (artifacts_dir / "run_card.json").write_text(
        json.dumps(
            {
                "sharpe": 1.5,
                "max_drawdown_pct": -0.05,
                "total_return_pct": 0.12,
            }
        )
    )

    async def fake_create_subprocess_exec(*cmd, **kwargs):
        fake_proc = AsyncMock()
        fake_proc.returncode = 0
        fake_proc.communicate.return_value = (b"", b"")
        return fake_proc

    monkeypatch.setattr(
        "runtime.vibe_bridge.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    pipelines_dir = m2_setup.runner._pipelines_dir
    (pipelines_dir / "backtest_demo.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "backtest_demo",
                "version": "1.0",
                "trigger": {"type": "manual"},
                "stages": [
                    {
                        "name": "backtest",
                        "tool": "vibe_tool",
                        "inputs": {
                            "capability": "backtest",
                            "inputs": {
                                "run_dir": str(run_dir),
                                "market": "crypto",
                                "symbols": ["SOLUSDT.P"],
                            },
                        },
                    }
                ],
            }
        )
    )

    run_id = await m2_setup.runner.run_pipeline("backtest_demo")
    run = await m2_setup.store.get_pipeline_run(run_id)
    assert run.status == RunStatus.completed
    artifact_names = {a.name for a in run.artifact_refs}
    assert {"equity.csv", "trades.csv", "metrics.csv", "run_card.json"} <= artifact_names


@pytest.mark.integration
@pytest.mark.asyncio
async def test_market_open_review_pipeline(m2_setup, tmp_path):
    m2_setup.registry._tools["ohlcv_tool"] = FakeOHLCVTool()

    pipelines_dir = m2_setup.runner._pipelines_dir
    (pipelines_dir / "market_open_review.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "market_open_review",
                "version": "1.0",
                "trigger": {
                    "type": "cron",
                    "cron": "0 9 * * 1-5",
                    "timezone": "Asia/Shanghai",
                },
                "stages": [
                    {
                        "name": "fetch_watchlist_ohlcv",
                        "tool": "ohlcv_tool",
                        "inputs": {
                            "symbol": "000001.SZ",
                            "market": "a_share",
                            "interval": "1d",
                        },
                    }
                ],
            }
        )
    )

    run_id = await m2_setup.runner.run_pipeline("market_open_review")
    run = await m2_setup.store.get_pipeline_run(run_id)
    assert run.status == RunStatus.completed
