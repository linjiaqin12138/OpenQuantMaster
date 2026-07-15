from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class PathsConfig(BaseModel):
    artifacts: Path = Path("./artifacts")
    logs: Path = Path("./logs")
    database: Path = Path("./data/runtime.db")


class SchedulerConfig(BaseModel):
    timezone: str = "UTC"


class EventBusConfig(BaseModel):
    backend: Literal["memory"] = "memory"


class LoggingConfig(BaseModel):
    level: str = "INFO"
    format: Literal["json", "console"] = "json"


class RuntimeConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="QUANT_AGENT_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    app_name: str = "OpenQuantMaster"
    environment: str = "development"
    paths: PathsConfig = PathsConfig()
    scheduler: SchedulerConfig = SchedulerConfig()
    event_bus: EventBusConfig = EventBusConfig()
    logging: LoggingConfig = LoggingConfig()
    config_path: Path | None = None

    @property
    def database_url(self) -> str:
        return f"sqlite+aiosqlite:///{self.paths.database}"


def _load_env_overrides(prefix: str = "QUANT_AGENT_") -> dict[str, Any]:
    """Read environment variables with the given prefix into a nested dict."""
    overrides: dict[str, Any] = {}
    for key, value in os.environ.items():
        if key.startswith(prefix):
            path = key[len(prefix) :].lower().split("__")
            target = overrides
            for part in path[:-1]:
                target = target.setdefault(part, {})
            target[path[-1]] = value
    # The project uses QUANT_AGENT_ENV to set the `environment` field.
    if "env" in overrides:
        overrides["environment"] = overrides.pop("env")
    return overrides


def load_config(config_path: Path | str | None = None, **overrides: Any) -> RuntimeConfig:
    """Load runtime configuration from YAML, environment, and CLI overrides."""
    kwargs: dict[str, Any] = {}
    if config_path is not None:
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        kwargs.update(raw)
        kwargs["config_path"] = path
    kwargs.update(_load_env_overrides())
    kwargs.update(overrides)
    return RuntimeConfig(**kwargs)
