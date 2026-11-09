from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError


class BinanceProviderConfig(BaseModel):
    """``providers.binance`` section of the external configuration."""

    api_key: str = Field(default="", alias="apiKey")
    secret: str = ""
    exchange: str | None = None
    product: str | None = None
    sandbox: bool = False


class TushareProviderConfig(BaseModel):
    """``providers.tushare`` section of the external configuration."""

    token: str = ""


class PushPlusProviderConfig(BaseModel):
    """``providers.pushplus`` section of the external configuration."""

    token: str = ""
    channel: str = "wechat"
    timeout_seconds: float = Field(default=10, gt=0, alias="timeout")


class ProvidersConfig(BaseModel):
    binance: BinanceProviderConfig = Field(default_factory=BinanceProviderConfig)
    tushare: TushareProviderConfig = Field(default_factory=TushareProviderConfig)
    pushplus: PushPlusProviderConfig = Field(default_factory=PushPlusProviderConfig)


class AppConfig(BaseModel):
    """The application's external configuration format."""

    providers: ProvidersConfig = Field(default_factory=ProvidersConfig)


def resolve_config_path(cli_path: str | Path | None = None) -> Path:
    if cli_path is not None:
        path = Path(cli_path).expanduser().resolve()
        if not path.is_file():
            raise RuntimeError(f"Config file not found: {path}")
        return path

    candidates = [Path.cwd() / "config.yaml", Path.home() / ".qm" / "config.yaml"]
    for path in candidates:
        if path.is_file():
            return path.resolve()

    searched = ", ".join(str(path) for path in candidates)
    raise RuntimeError(f"No config file found. Searched: {searched}")


def load_config(path: str | Path | None = None) -> AppConfig:
    config_path = resolve_config_path(path)
    try:
        with config_path.open(encoding="utf-8") as file:
            raw = yaml.safe_load(file) or {}
        return AppConfig.model_validate(raw)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise RuntimeError(f"Failed to load config {config_path}: {exc}") from exc
