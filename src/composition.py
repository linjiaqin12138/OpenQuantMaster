"""Composition boundary.

This module reads the application's external configuration and constructs the
component-owned Config classes of the capabilities it wires up, then calls the
Service constructors with them. It is the only place that knows both the
external configuration format and the internal configuration contracts of the
services.
"""

from __future__ import annotations

from src.config import AppConfig
from src.services.binance_perp import BinancePerp, BinancePerpServiceConfig
from src.services.indicator import Indicator, IndicatorServiceConfig
from src.services.notification import NotificationService, NotificationServiceConfig
from src.services.ohlcv import OHLCV, OHLCVServiceConfig

__all__ = [
    "build_binance_perp_service",
    "build_indicator_service",
    "build_notification_service",
    "build_ohlcv_service",
]


def build_ohlcv_service(config: AppConfig) -> OHLCV:
    """Build the market-data service for the configured providers."""
    binance = config.providers.binance
    return OHLCV(
        OHLCVServiceConfig(
            exchange=binance.exchange or "binance",
            product=binance.product or "spot",
            sandbox=binance.sandbox,
            api_key=binance.api_key,
            secret=binance.secret,
            tushare_token=config.providers.tushare.token,
        )
    )


def build_indicator_service(config: AppConfig) -> Indicator:
    """Build the technical-analysis service for the configured providers."""
    binance = config.providers.binance
    return Indicator(
        IndicatorServiceConfig(
            exchange=binance.exchange or "binance",
            product=binance.product or "spot",
            sandbox=binance.sandbox,
            api_key=binance.api_key,
            secret=binance.secret,
            tushare_token=config.providers.tushare.token,
        )
    )


def build_notification_service(config: AppConfig) -> NotificationService:
    """Build the notification service for the configured provider."""
    pushplus = config.providers.pushplus
    return NotificationService(
        NotificationServiceConfig(
            provider="pushplus",
            token=pushplus.token,
            channel=pushplus.channel,
            timeout_seconds=pushplus.timeout_seconds,
        )
    )


def build_binance_perp_service(config: AppConfig) -> BinancePerp:
    """Build the perpetual-futures service for the configured exchange."""
    binance = config.providers.binance
    return BinancePerp(
        BinancePerpServiceConfig(
            exchange=binance.exchange or "binance",
            product=binance.product or "usdm",
            sandbox=binance.sandbox,
            api_key=binance.api_key,
            secret=binance.secret,
        )
    )
