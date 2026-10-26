
import pytest

from runtime.config_loader import load_config


@pytest.mark.unit
def test_config_loads_exchanges_and_refs(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
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
exchanges:
  binance:
    apiKey: test-key
    secret: test-secret
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
    tushare_token: test-token
    yfinance_timeout: 30
execution:
  binance_perp:
    exchange: binance
    product: usdm
"""
    )
    cfg = load_config(config_path)
    assert cfg.market_data.crypto.exchange == "binance"
    assert cfg.market_data.crypto.product == "spot"
    assert cfg.exchanges.binance.apiKey == "test-key"
    assert cfg.exchanges.binance.spot.ccxt_id == "binance"
    assert cfg.exchanges.binance.usdm.ccxt_id == "binanceusdm"
    assert cfg.exchanges.binance.usdm.sandbox is True
    assert cfg.execution.binance_perp.product == "usdm"
    assert cfg.market_data.equities.tushare_token == "test-token"


@pytest.mark.unit
def test_product_credential_override_in_config(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
exchanges:
  binance:
    apiKey: root-key
    secret: root-secret
    usdm:
      ccxt_id: binanceusdm
      sandbox: true
      apiKey: futures-key
      secret: futures-secret
"""
    )
    cfg = load_config(config_path)
    assert cfg.exchanges.binance.apiKey == "root-key"
    assert cfg.exchanges.binance.usdm.apiKey == "futures-key"
    assert cfg.exchanges.binance.usdm.secret == "futures-secret"
    assert cfg.exchanges.binance.spot.apiKey is None


@pytest.mark.unit
def test_exchange_defaults_without_yaml_block(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = load_config()
    assert cfg.exchanges.binance.usdm.ccxt_id == "binanceusdm"
    assert cfg.exchanges.binance.usdm.sandbox is True
    assert cfg.exchanges.binance.spot.sandbox is False
    assert cfg.execution.binance_perp.exchange == "binance"
