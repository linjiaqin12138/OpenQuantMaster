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


@pytest.mark.unit
def test_load_config_defaults_to_cwd_config_yaml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "config.yaml"
    config_path.write_text("app_name: FromCWD\nenvironment: testing\n")
    cfg = load_config()
    assert cfg.app_name == "FromCWD"
    assert cfg.environment == "testing"
    assert cfg.config_path == Path("config.yaml")


@pytest.mark.unit
def test_load_config_ignores_missing_default_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = load_config()
    assert cfg.app_name == "OpenQuantMaster"
    assert cfg.config_path is None


@pytest.mark.unit
def test_agent_config_defaults():
    from runtime.config_loader import AgentConfig

    config = AgentConfig()
    assert config.adapter == "claude"
    assert config.default_cli == "claude"
    assert config.timeout_sec == 120
    assert config.workdir == ""
    assert config.headless_args == []
    assert config.generic.prompt_flag == "-p"


@pytest.mark.unit
def test_agent_config_generic_adapter():
    from runtime.config_loader import AgentConfig

    config = AgentConfig(adapter="generic", default_cli="mycli", generic={"prompt_flag": "--prompt"})
    assert config.adapter == "generic"
    assert config.generic.prompt_flag == "--prompt"


@pytest.mark.unit
def test_agent_config_rejects_removed_fields():
    from runtime.config_loader import AgentConfig

    # pydantic v2 default extra="ignore" (this file's convention), so removed
    # fields are silently ignored; assert they no longer exist on the model.
    assert not hasattr(AgentConfig(), "custom_command")
    assert not hasattr(AgentConfig(custom_command="echo hi"), "custom_command")
