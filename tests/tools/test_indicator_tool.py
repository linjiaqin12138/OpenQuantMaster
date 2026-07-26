import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest
import talib

from tools.base.tool_registry import ToolRegistry
from tools.market_data.indicator_tool import IndicatorTool


def _make_ohlcv_fixture(n: int = 50) -> str:
    """Return CSV content with at least one detectable candlestick pattern."""
    np.random.seed(42)
    base = 100 + np.cumsum(np.random.randn(n) * 0.5)
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=n, freq="h", tz="UTC"),
            "open": base,
            "high": base + np.abs(np.random.randn(n)) * 1.5,
            "low": base - np.abs(np.random.randn(n)) * 1.5,
            "close": base + np.random.randn(n) * 1.0,
            "volume": np.random.randint(1000, 10000, n),
        }
    )
    # Force a doji (open == close) at a specific index.
    df.loc[10, ["open", "high", "low", "close"]] = [100.0, 100.5, 99.5, 100.0]
    # Force a bullish engulfing pattern around index 30.
    df.loc[29, ["open", "high", "low", "close"]] = [102.0, 102.2, 100.5, 100.8]
    df.loc[30, ["open", "high", "low", "close"]] = [100.0, 103.0, 99.5, 102.5]
    return df.to_csv(index=False)


def _write_config(tmp_path: Path) -> None:
    (tmp_path / "config.yaml").write_text(
        """
app_name: OpenQuantMaster
environment: testing
paths:
  artifacts: ./artifacts
  logs: ./logs
  database: ./data/runtime.db
scheduler:
  timezone: UTC
event_bus:
  backend: memory
logging:
  level: INFO
  format: json
""",
        encoding="utf-8",
    )


@pytest.fixture
def ohlcv_csv(tmp_path: Path) -> str:
    csv_content = _make_ohlcv_fixture()
    artifact_dir = tmp_path / "artifacts" / "run-123" / "ohlcv_tool"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "ohlcv_BTCUSDT_1h.csv"
    artifact_path.write_text(csv_content, encoding="utf-8")
    return str(artifact_path)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_indicator_tool_from_artifact(tmp_path: Path, ohlcv_csv: str, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    tool = IndicatorTool()
    result = await tool.execute(
        {
            "source": "ohlcv_artifact",
            "artifact": ohlcv_csv,
            "interval": "1h",
            "indicators": ["sma", "ema", "macd", "rsi", "boll", "atr"],
            "patterns": ["DOJI", "ENGULFING"],
            "pipeline_run_id": "run-123",
        }
    )

    assert result.success is True
    data = result.data
    assert "BTCUSDT" in data["symbol"]
    assert data["interval"] == "1h"
    assert data["rows"] == 50

    indicators = data["indicators"]
    assert "sma" in indicators
    assert "rsi" in indicators
    assert 0 <= indicators["rsi"]["value"] <= 100
    assert indicators["sma"]["value"] > 0
    assert indicators["sma"]["params"]["timeperiod"] == 30
    assert indicators["boll"]["upperband"] >= indicators["boll"]["middleband"]
    assert indicators["boll"]["middleband"] >= indicators["boll"]["lowerband"]
    assert indicators["macd"]["params"]["fastperiod"] == 12

    patterns = data["patterns"]
    assert patterns["last_bullish"] is not None or patterns["last_bearish"] is not None
    assert any(entry["pattern"] == "DOJI" for entry in patterns["history"])
    assert data["summary"]
    assert "BTCUSDT" in data["summary"]
    assert "1h" in data["summary"]

    assert len(result.artifacts) == 1
    assert result.artifacts[0].name == "indicator_result.json"
    artifact_path = tmp_path / "artifacts" / "run-123" / "indicator_tool" / "indicator_result.json"
    assert artifact_path.exists()
    saved = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert saved["rows"] == 50
    assert saved["summary"] == data["summary"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_indicator_tool_from_symbol_mock(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    csv_content = _make_ohlcv_fixture()
    fake_artifact = MagicMock()
    fake_artifact.content = csv_content
    fake_result = MagicMock()
    fake_result.success = True
    fake_result.error = None
    fake_result.artifacts = [fake_artifact]

    with patch(
        "tools.market_data.ohlcv_tool.OHLCVTool.execute", new=AsyncMock(return_value=fake_result)
    ):
        tool = IndicatorTool()
        result = await tool.execute(
            {
                "source": "symbol",
                "symbol": "BTC/USDT",
                "market": "crypto",
                "interval": "1h",
                "limit": 50,
                "pipeline_run_id": "run-456",
            }
        )

    assert result.success is True
    assert result.data["symbol"] == "BTC/USDT"
    assert result.data["rows"] == 50
    assert result.data["indicators"]["rsi"]["value"] is not None
    assert result.data["patterns"] == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_indicator_tool_rejects_insufficient_data(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(
        "app_name: OpenQuantMaster\nenvironment: testing\n", encoding="utf-8"
    )

    small_df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=3, freq="h", tz="UTC"),
            "open": [100.0, 101.0, 102.0],
            "high": [101.0, 102.0, 103.0],
            "low": [99.0, 100.0, 101.0],
            "close": [100.5, 101.5, 102.5],
            "volume": [1000, 2000, 3000],
        }
    )
    artifact_dir = tmp_path / "artifacts" / "run-789" / "ohlcv_tool"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_dir / "small.csv"
    artifact_path.write_text(small_df.to_csv(index=False), encoding="utf-8")

    tool = IndicatorTool()
    result = await tool.execute(
        {
            "source": "ohlcv_artifact",
            "artifact": str(artifact_path),
            "indicators": ["sma", "macd"],
            "patterns": ["DOJI"],
        }
    )

    assert result.success is False
    assert "Insufficient data" in result.error
    assert "33" in result.error


@pytest.mark.unit
@pytest.mark.asyncio
async def test_indicator_tool_rejects_missing_artifact(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.yaml").write_text(
        "app_name: OpenQuantMaster\nenvironment: testing\n", encoding="utf-8"
    )

    tool = IndicatorTool()
    result = await tool.execute(
        {
            "source": "ohlcv_artifact",
            "artifact": str(tmp_path / "nonexistent.csv"),
        }
    )
    assert result.success is False
    assert "not found" in result.error.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_indicator_tool_dynamic_indicators(tmp_path: Path, ohlcv_csv: str, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    tool = IndicatorTool()
    result = await tool.execute(
        {
            "source": "ohlcv_artifact",
            "artifact": ohlcv_csv,
            "indicators": ["ADX", "OBV", "STOCH"],
        }
    )

    assert result.success is True
    indicators = result.data["indicators"]
    assert "ADX" in indicators
    assert indicators["ADX"]["value"] is not None
    assert "OBV" in indicators
    assert indicators["OBV"]["value"] is not None
    assert "STOCH" in indicators
    assert indicators["STOCH"]["slowk"] is not None
    assert indicators["STOCH"]["slowd"] is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_indicator_tool_indicator_params(tmp_path: Path, ohlcv_csv: str, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    tool = IndicatorTool()
    result = await tool.execute(
        {
            "source": "ohlcv_artifact",
            "artifact": ohlcv_csv,
            "indicators": ["sma", "macd"],
            "indicator_params": {
                "SMA": {"timeperiod": 10},
                "MACD": {"fastperiod": 5, "slowperiod": 15, "signalperiod": 3},
            },
        }
    )

    assert result.success is True
    sma = result.data["indicators"]["sma"]
    assert sma["params"]["timeperiod"] == 10
    macd = result.data["indicators"]["macd"]
    assert macd["params"]["fastperiod"] == 5
    assert macd["params"]["slowperiod"] == 15
    assert macd["params"]["signalperiod"] == 3


@pytest.mark.unit
@pytest.mark.asyncio
async def test_indicator_tool_patterns_default_none(tmp_path: Path, ohlcv_csv: str, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    tool = IndicatorTool()
    result = await tool.execute(
        {
            "source": "ohlcv_artifact",
            "artifact": ohlcv_csv,
            "indicators": ["rsi"],
        }
    )

    assert result.success is True
    assert result.data["patterns"] == {}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_indicator_tool_patterns_bare_names(tmp_path: Path, ohlcv_csv: str, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    tool = IndicatorTool()
    result = await tool.execute(
        {
            "source": "ohlcv_artifact",
            "artifact": ohlcv_csv,
            "indicators": ["rsi"],
            "patterns": ["ENGULFING", "DOJI", "HAMMER"],
        }
    )

    assert result.success is True
    patterns = result.data["patterns"]
    assert isinstance(patterns["history"], list)
    if patterns["history"]:
        entry = patterns["history"][0]
        assert "pattern" in entry
        assert "label" in entry
        assert entry["label"] in ("bullish", "bearish", "neutral")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_indicator_tool_patterns_all_61(tmp_path: Path, ohlcv_csv: str, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    all_patterns = [name[3:] for name in talib.get_functions() if name.startswith("CDL")]
    assert len(all_patterns) == 61

    tool = IndicatorTool()
    result = await tool.execute(
        {
            "source": "ohlcv_artifact",
            "artifact": ohlcv_csv,
            "indicators": ["SMA"],
            "patterns": all_patterns,
        }
    )

    assert result.success is True
    patterns = result.data["patterns"]
    assert isinstance(patterns["history"], list)
    if patterns["history"]:
        assert patterns["last_bullish"] is not None or patterns["last_bearish"] is not None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_indicator_tool_rejects_unknown_indicator(tmp_path: Path, ohlcv_csv: str, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    tool = IndicatorTool()
    result = await tool.execute(
        {
            "source": "ohlcv_artifact",
            "artifact": ohlcv_csv,
            "indicators": ["NOT_AN_INDICATOR"],
        }
    )

    assert result.success is False
    assert "Unknown indicator function" in result.error


@pytest.mark.unit
@pytest.mark.asyncio
async def test_indicator_tool_runtime_failed_indicator(tmp_path: Path, ohlcv_csv: str, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_config(tmp_path)

    tool = IndicatorTool()
    result = await tool.execute(
        {
            "source": "ohlcv_artifact",
            "artifact": ohlcv_csv,
            "indicators": ["MAVP"],
        }
    )

    assert result.success is True
    assert "MAVP" in result.data["indicators"]
    assert "error" in result.data["indicators"]["MAVP"]


@pytest.mark.unit
def test_registry_discovers_indicator_tool():
    import tools

    registry = ToolRegistry()
    count = registry.discover(tools)
    assert count >= 1
    assert "indicator_tool" in registry.list_tools()


@pytest.mark.unit
def test_indicator_tool_no_arg_constructor():
    tool = IndicatorTool()
    assert tool.name == "indicator_tool"
    assert "indicators" in tool.input_schema["properties"]
    assert "indicator_params" in tool.input_schema["properties"]
    assert "patterns" in tool.input_schema["properties"]
