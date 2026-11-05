from src.entry.cli.base import register_service
from src.entry.cli.services.binance_perp import binance_perp, render_binance_perp
from src.entry.cli.services.indicator import indicator, render_indicator
from src.entry.cli.services.ohlcv import ohlcv, render_ohlcv


def register_services() -> None:
    register_service(binance_perp, renderer=render_binance_perp)
    register_service(indicator, renderer=render_indicator)
    register_service(ohlcv, renderer=render_ohlcv)
