from __future__ import annotations

from typing import Any

import pytest

from src.config import AppConfig


@pytest.fixture
def app_config() -> AppConfig:
    """External configuration used to build services under test."""
    return AppConfig.model_validate(
        {
            "providers": {
                "binance": {"apiKey": "key", "secret": "secret"},
                "tushare": {"token": "tushare-token"},
                "pushplus": {"token": "pushplus-token", "channel": "wechat", "timeout": 5},
            }
        }
    )


def make_app_config(**providers: Any) -> AppConfig:
    """Build an external configuration from provider sections."""
    return AppConfig.model_validate({"providers": providers})
