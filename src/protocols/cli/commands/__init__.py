from src.protocols.cli.base import register_service
from src.protocols.cli.commands.binance_perp import binance_perp, render_binance_perp
from src.protocols.cli.commands.indicator import indicator, render_indicator
from src.protocols.cli.commands.news_fetcher import news_fetcher, render_news_fetcher
from src.protocols.cli.commands.notification import notification, render_notification
from src.protocols.cli.commands.ohlcv import ohlcv, render_ohlcv


def register_services() -> None:
    register_service(binance_perp, renderer=render_binance_perp)
    register_service(indicator, renderer=render_indicator)
    register_service(news_fetcher, renderer=render_news_fetcher)
    register_service(notification, renderer=render_notification)
    register_service(ohlcv, renderer=render_ohlcv)
