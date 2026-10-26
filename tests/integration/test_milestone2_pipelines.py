from typing import Any, ClassVar

import pytest
import pytest_asyncio
import yaml
from pydantic import BaseModel

from runtime.bootstrap import bootstrap
from runtime.state_store.models import RunStatus
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
exchanges:
  binance:
    apiKey: ""
    secret: ""
    spot:
      ccxt_id: binance
      sandbox: false
    usdm:
      ccxt_id: binanceusdm
      sandbox: true
market_data:
  crypto:
    exchange: binance
    product: spot
  equities:
    tushare_token: ""
    yfinance_timeout: 30
execution:
  binance_perp:
    exchange: binance
    product: usdm
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
