from pathlib import Path

import pytest

from src.config import load_config, resolve_config_path


def test_explicit_config_path_has_priority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    explicit = tmp_path / "explicit.yaml"
    explicit.write_text("providers:\n  tushare:\n    token: explicit\n", encoding="utf-8")
    local = tmp_path / "config.yaml"
    local.write_text("providers:\n  tushare:\n    token: local\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    assert resolve_config_path(explicit) == explicit.resolve()
    assert load_config(explicit).providers.tushare.token == "explicit"


def test_local_config_has_priority_over_home_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    work = tmp_path / "work"
    home = tmp_path / "home"
    work.mkdir()
    (home / ".qm").mkdir(parents=True)
    (work / "config.yaml").write_text("providers:\n  tushare:\n    token: local\n", encoding="utf-8")
    (home / ".qm" / "config.yaml").write_text(
        "providers:\n  tushare:\n    token: home\n", encoding="utf-8"
    )
    monkeypatch.chdir(work)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    assert resolve_config_path() == (work / "config.yaml").resolve()
    monkeypatch.chdir(tmp_path)
    assert resolve_config_path() == (home / ".qm" / "config.yaml").resolve()


def test_missing_explicit_config_path_fails(tmp_path: Path):
    with pytest.raises(RuntimeError, match="Config file not found"):
        resolve_config_path(tmp_path / "missing.yaml")


def test_load_config_parses_provider_models(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text(
        'providers:\n  binance:\n    apiKey: key\n    secret: secret\n  tushare:\n    token: token\n',
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.providers.binance.api_key == "key"
    assert config.providers.binance.secret == "secret"
    assert config.providers.tushare.token == "token"
    assert config.providers.pushplus.channel == "wechat"
    assert config.providers.pushplus.timeout_seconds == 10


def test_load_config_parses_notification_provider(tmp_path: Path):
    path = tmp_path / "config.yaml"
    path.write_text(
        "providers:\n  pushplus:\n    token: pushplus-token\n    timeout: 5\n",
        encoding="utf-8",
    )

    config = load_config(path)

    assert config.providers.pushplus.token == "pushplus-token"
    assert config.providers.pushplus.timeout_seconds == 5
