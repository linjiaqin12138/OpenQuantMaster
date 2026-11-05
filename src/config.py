from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError


class BinanceProviderConfig(BaseModel):
    api_key: str = Field(default="", alias="apiKey")
    secret: str = ""


class TushareProviderConfig(BaseModel):
    token: str = ""


class ProvidersConfig(BaseModel):
    binance: BinanceProviderConfig = Field(default_factory=BinanceProviderConfig)
    tushare: TushareProviderConfig = Field(default_factory=TushareProviderConfig)


class AppConfig(BaseModel):
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
