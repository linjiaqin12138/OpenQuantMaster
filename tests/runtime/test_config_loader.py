from pathlib import Path

import pytest

from runtime.config_loader import load_config


@pytest.mark.unit
def test_load_config_defaults(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
app_name: OpenQuantMaster
environment: development
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
"""
    )
    cfg = load_config(config_path)
    assert cfg.app_name == "OpenQuantMaster"
    assert cfg.environment == "development"
    assert cfg.paths.artifacts == Path("./artifacts")
    assert cfg.scheduler.timezone == "UTC"
    assert cfg.logging.level == "INFO"


@pytest.mark.unit
def test_env_override(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("app_name: OpenQuantMaster\nenvironment: development\n")
    monkeypatch.setenv("QUANT_AGENT_ENV", "testing")
    cfg = load_config(config_path)
    assert cfg.environment == "testing"
