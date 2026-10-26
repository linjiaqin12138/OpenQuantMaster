
import pytest

from runtime.config_loader import load_config


@pytest.mark.unit
def test_config_loads_market_data(tmp_path, monkeypatch):
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
market_data:
  crypto:
    default_exchange: binance
    sandbox: false
    exchange_keys:
      binance:
        apiKey: test-key
        secret: test-secret
  equities:
    tushare_token: test-token
    yfinance_timeout: 30
"""
    )
    cfg = load_config(config_path)
    assert cfg.market_data.crypto.default_exchange == "binance"
    assert cfg.market_data.crypto.exchange_keys["binance"]["apiKey"] == "test-key"
    assert cfg.market_data.equities.tushare_token == "test-token"
