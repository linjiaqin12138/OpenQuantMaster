from __future__ import annotations

import logging

import structlog

from runtime.config_loader import RuntimeConfig


def configure_logging(cfg: RuntimeConfig) -> None:
    """Configure structlog and stdlib logging from RuntimeConfig.

    Both CLI and daemon entry points should call this before doing any work
    so that ``config.logging.level`` and ``config.logging.format`` take effect.
    """
    level = getattr(logging, cfg.logging.level.upper(), logging.INFO)
    logging.basicConfig(level=level, force=True)

    shared_processors = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if cfg.logging.format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
