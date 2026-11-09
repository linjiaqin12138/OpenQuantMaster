from __future__ import annotations

import json
from typing import Any

import click
import pytest
from click.testing import CliRunner

from src.models.result import Error, Result, ServiceResult
from src.protocols.cli.base import echo_service_result, main

BAR = {
    "timestamp": "2026-01-01T00:00:00Z",
    "open": 100.0,
    "high": 110.0,
    "low": 90.0,
    "close": 105.0,
    "volume": 1000.0,
}


@pytest.fixture
def config_file(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "providers:\n  binance:\n    apiKey: \"\"\n    secret: \"\"\n",
        encoding="utf-8",
    )
    return path


def _provider(data: list[dict[str, Any]]):
    async def _call(**kwargs: Any) -> Result:
        return Result(success=True, data=data)

    return _call


def _failing_provider(code: str):
    async def _call(**kwargs: Any) -> Result:
        return Result(success=False, error=Error(code=code, message="provider failed"))

    return _call


def _run(config_file, *args: str):
    return CliRunner().invoke(main, ["--config", str(config_file), "run", *args])


@pytest.mark.unit
def test_list_shows_every_service():
    result = CliRunner().invoke(main, ["list"])

    assert result.exit_code == 0
    assert "ohlcv" in result.output
    assert "indicator" in result.output


@pytest.mark.unit
def test_the_json_output_contains_only_the_service_data(config_file, monkeypatch):
    monkeypatch.setattr(
        "src.use_cases.ohlcv.fetch_crypto_ohlcv_result",
        _provider([BAR]),
    )

    result = _run(
        config_file,
        "ohlcv",
        "--symbol",
        "BTCUSDT",
        "--market",
        "crypto",
        "--interval",
        "1h",
        "-o",
        "json",
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["symbol"] == "BTCUSDT"
    assert payload["bars"][0]["close"] == 105.0


@pytest.mark.unit
def test_a_service_error_is_mapped_to_a_cli_code(config_file, monkeypatch):
    monkeypatch.setattr(
        "src.use_cases.ohlcv.fetch_crypto_ohlcv_result",
        _failing_provider("provider_unavailable"),
    )

    result = _run(
        config_file,
        "ohlcv",
        "--symbol",
        "BTCUSDT",
        "--market",
        "crypto",
        "--interval",
        "1h",
        "-o",
        "json",
    )

    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "MARKET_DATA_UNAVAILABLE"


@pytest.mark.unit
def test_an_unmapped_service_error_falls_back_to_the_generic_code(capsys):
    result = ServiceResult(
        success=False,
        error=Error(code="a_service_code_the_cli_does_not_know", message="boom"),
    )

    with pytest.raises(click.exceptions.Exit):
        echo_service_result(result, "ohlcv", "json")

    payload = json.loads(capsys.readouterr().err)
    assert payload["error"]["code"] == "ACTION_FAILED"


@pytest.mark.unit
def test_an_invalid_request_is_mapped_to_invalid_input(config_file):
    result = _run(
        config_file,
        "ohlcv",
        "--symbol",
        "BTCUSDT",
        "--market",
        "crypto",
        "--interval",
        "1h",
        "--limit",
        "9999",
        "-o",
        "json",
    )

    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "INVALID_INPUT"


@pytest.mark.unit
def test_an_unexpected_failure_becomes_an_internal_error(config_file, monkeypatch):
    async def _call(**kwargs: Any) -> Result:
        raise RuntimeError("boom")

    monkeypatch.setattr("src.use_cases.ohlcv.fetch_crypto_ohlcv_result", _call)

    result = _run(
        config_file,
        "ohlcv",
        "--symbol",
        "BTCUSDT",
        "--market",
        "crypto",
        "--interval",
        "1h",
        "-o",
        "json",
    )

    assert result.exit_code == 1
    payload = json.loads(result.stderr)
    assert payload["error"]["code"] == "INTERNAL_ERROR"
    assert "boom" in payload["error"]["message"]


@pytest.mark.unit
def test_a_jsonpath_selection_applies_to_the_service_data(config_file, monkeypatch):
    monkeypatch.setattr(
        "src.use_cases.ohlcv.fetch_crypto_ohlcv_result",
        _provider([BAR]),
    )

    result = _run(
        config_file,
        "ohlcv",
        "--symbol",
        "BTCUSDT",
        "--market",
        "crypto",
        "--interval",
        "1h",
        "-o",
        "jsonpath={.rows}",
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == 1
