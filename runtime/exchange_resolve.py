from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from runtime.config_loader import RuntimeConfig

BinanceProductName = Literal["spot", "usdm"]


@dataclass(frozen=True)
class ResolvedExchange:
    """Resolved ccxt connection params for a named exchange product."""

    exchange: str
    product: str
    ccxt_id: str
    sandbox: bool
    api_key: str
    secret: str

    def ccxt_options(self) -> dict[str, str | bool]:
        opts: dict[str, str | bool] = {"enableRateLimit": True}
        if self.api_key:
            opts["apiKey"] = self.api_key
        if self.secret:
            opts["secret"] = self.secret
        return opts


def resolve_exchange(
    cfg: RuntimeConfig,
    exchange: str,
    product: BinanceProductName,
) -> ResolvedExchange:
    """Resolve credentials and connection settings from top-level exchanges config."""
    if exchange != "binance":
        raise ValueError(f"Unsupported exchange reference: {exchange!r}")

    venue = cfg.exchanges.binance
    product_cfg = getattr(venue, product)
    api_key = product_cfg.apiKey if product_cfg.apiKey else venue.apiKey
    secret = product_cfg.secret if product_cfg.secret else venue.secret
    return ResolvedExchange(
        exchange=exchange,
        product=product,
        ccxt_id=product_cfg.ccxt_id,
        sandbox=product_cfg.sandbox,
        api_key=api_key or "",
        secret=secret or "",
    )
