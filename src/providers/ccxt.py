from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import math

from src.models.result import AppError, Error, as_call_result

# Adapter map only - callers use logical exchange/product names.
_CCXT_EXCHANGE_IDS: dict[tuple[str, str], str] = {
    ("binance", "spot"): "binance",
    ("binance", "usdm"): "binanceusdm",
}

DEFAULT_TIMEOUT_MS = 10_000


@dataclass(frozen=True)
class CcxtVenue:
    """Venue coordinates needed to open a CCXT client."""

    exchange: str = "binance"
    product: str = "usdm"
    sandbox: bool = False
    api_key: str = ""
    secret: str = ""


def _build_client(venue: CcxtVenue, *, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> Any:
    import ccxt.async_support as ccxt

    adapter_id = _CCXT_EXCHANGE_IDS.get((venue.exchange, venue.product))
    if adapter_id is None:
        raise AppError(
            "provider_unsupported_venue",
            f"Unsupported venue: exchange={venue.exchange!r} product={venue.product!r}",
        )
    exchange_class = getattr(ccxt, adapter_id, None)
    if exchange_class is None:
        raise AppError(
            "provider_unsupported_venue",
            f"Exchange adapter unavailable for venue: {venue.exchange}/{venue.product}",
        )

    options: dict[str, Any] = {"enableRateLimit": True, "timeout": timeout_ms}
    if venue.api_key:
        options["apiKey"] = venue.api_key
    if venue.secret:
        options["secret"] = venue.secret
    client = exchange_class(options)
    if venue.sandbox and hasattr(client, "set_sandbox_mode"):
        client.set_sandbox_mode(True)
    return client


def _normalize_ohlcv_rows(rows: list[list[float]]) -> list[dict[str, Any]]:
    bars: list[dict[str, Any]] = []
    for row in rows:
        timestamp, open_, high, low, close, volume = row[:6]
        bars.append(
            {
                "timestamp": datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                "open": float(open_),
                "high": float(high),
                "low": float(low),
                "close": float(close),
                "volume": float(volume),
            }
        )
    return bars


async def fetch_crypto_ohlcv(
    *,
    venue: CcxtVenue,
    symbol: str,
    interval: str,
    limit: int = 1000,
    since_ms: int | None = None,
    until_ms: int | None = None,
) -> list[dict[str, Any]]:
    """Fetch OHLCV bars from a CCXT venue and normalize them to plain bars."""
    client = _build_client(venue)
    try:
        if since_ms is not None:
            raw = await client.fetch_ohlcv(symbol, interval, since=since_ms, limit=limit)
        else:
            raw = await client.fetch_ohlcv(symbol, interval, limit=limit)
    finally:
        await client.close()

    bars = _normalize_ohlcv_rows(raw)
    if until_ms is not None:
        bars = [bar for bar in bars if _to_ms(bar["timestamp"]) <= until_ms]
    return bars


async def fetch_crypto_ticker(*, venue: CcxtVenue, symbol: str) -> dict[str, Any]:
    """Fetch the latest ticker of one crypto symbol from a CCXT venue."""
    client = _build_client(venue)
    try:
        raw = await client.fetch_ticker(symbol)
    finally:
        await client.close()
    return _normalize_crypto_ticker(raw)


async def fetch_balance(*, venue: CcxtVenue) -> dict[str, Any]:
    """Fetch the account balance and keep only the assets with a non-zero amount."""
    client = _build_client(venue)
    try:
        raw = await client.fetch_balance()
    finally:
        await client.close()
    return _trim_balance(raw)


async def fetch_positions(*, venue: CcxtVenue, symbol: str | None = None) -> list[dict[str, Any]]:
    """Fetch open positions, optionally restricted to one symbol."""
    client = _build_client(venue)
    try:
        raw = await client.fetch_positions([symbol] if symbol else None)
    finally:
        await client.close()
    return [_trim_position(position) for position in raw]


async def fetch_open_orders(
    *,
    venue: CcxtVenue,
    symbol: str,
    include_conditional: bool = True,
) -> list[dict[str, Any]]:
    """Fetch resting orders and, optionally, conditional (algo) orders."""
    client = _build_client(venue)
    try:
        resting = await client.fetch_open_orders(symbol)
        trimmed = [_trim_order(order, order_kind="resting") for order in resting]
        if not include_conditional:
            return trimmed
        conditional = await client.fetch_open_orders(symbol, params={"stop": True})
        trimmed.extend(_trim_order(order, order_kind="conditional") for order in conditional)
        return trimmed
    finally:
        await client.close()


async def create_order(
    *,
    venue: CcxtVenue,
    symbol: str,
    order_type: str,
    side: str,
    amount: float,
    price: float | None,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Submit an order and normalize the exchange answer."""
    client = _build_client(venue)
    try:
        raw = await client.create_order(symbol, order_type, side, amount, price, params or {})
    finally:
        await client.close()
    return _trim_order(raw)


async def cancel_order(*, venue: CcxtVenue, order_id: str, symbol: str) -> dict[str, Any]:
    """Cancel an open order and normalize the exchange answer."""
    client = _build_client(venue)
    try:
        raw = await client.cancel_order(order_id, symbol)
    finally:
        await client.close()
    return _trim_order(raw)


async def set_leverage(*, venue: CcxtVenue, leverage: int, symbol: str) -> dict[str, Any]:
    client = _build_client(venue)
    try:
        return await client.set_leverage(leverage, symbol)
    finally:
        await client.close()


async def set_margin_mode(*, venue: CcxtVenue, margin_mode: str, symbol: str) -> dict[str, Any]:
    client = _build_client(venue)
    try:
        return await client.set_margin_mode(margin_mode, symbol)
    finally:
        await client.close()


async def set_position_mode(*, venue: CcxtVenue, hedge: bool) -> dict[str, Any]:
    client = _build_client(venue)
    try:
        return await client.set_position_mode(hedge)
    finally:
        await client.close()


def map_ccxt_error(exc: Exception) -> Error | None:
    # The error classes live in the shared base package, so they stay importable
    # even when the async client module is replaced in tests.
    import ccxt

    if isinstance(exc, (ccxt.AuthenticationError, ccxt.PermissionDenied)):
        return Error(code="provider_unauthorized", message=str(exc), exception=exc)
    if isinstance(exc, (ccxt.RateLimitExceeded, ccxt.DDoSProtection)):
        return Error(code="provider_rate_limited", message=str(exc), exception=exc)
    if isinstance(exc, ccxt.RequestTimeout):
        return Error(code="provider_timeout", message=str(exc), exception=exc)
    if isinstance(exc, (ccxt.NetworkError, ccxt.ExchangeNotAvailable)):
        return Error(code="provider_unavailable", message=str(exc), exception=exc)
    if isinstance(exc, (ccxt.InvalidOrder, ccxt.BadRequest, ccxt.InsufficientFunds)):
        return Error(code="provider_rejected", message=str(exc), exception=exc)
    return None


def _normalize_crypto_ticker(raw: dict[str, Any]) -> dict[str, Any]:
    info = raw.get("info") if isinstance(raw.get("info"), dict) else {}
    price = _first_number(raw.get("last"), raw.get("close"))
    if price is None:
        raise ValueError("CCXT ticker contains no last price")
    timestamp = raw.get("timestamp")
    quote_time = None
    if isinstance(timestamp, (int, float)) and timestamp > 0:
        quote_time = (
            datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )
    elif raw.get("datetime"):
        quote_time = str(raw["datetime"])
    return {
        "name": str(raw.get("symbol") or ""),
        "price": price,
        "previous_close": _first_number(
            raw.get("previousClose"), info.get("prevClosePrice")
        ),
        "open": _first_number(raw.get("open"), info.get("openPrice")),
        "high": _first_number(raw.get("high"), info.get("highPrice")),
        "low": _first_number(raw.get("low"), info.get("lowPrice")),
        "change": _first_number(raw.get("change"), info.get("priceChange")),
        "change_percent": _first_number(raw.get("percentage"), info.get("priceChangePercent")),
        "bid": _first_number(raw.get("bid"), info.get("bidPrice")),
        "ask": _first_number(raw.get("ask"), info.get("askPrice")),
        "quote_time": quote_time,
    }


def _first_number(*values: Any) -> float | None:
    for value in values:
        if value is None or isinstance(value, bool):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(number):
            return number
    return None


def _to_ms(timestamp: str) -> int:
    parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return int(parsed.timestamp() * 1000)


def _trim_balance(raw: dict[str, Any]) -> dict[str, Any]:
    total = raw.get("total") or {}
    free = raw.get("free") or {}
    used = raw.get("used") or {}
    assets = sorted(
        {
            asset
            for asset in set(total) | set(free) | set(used)
            if any(
                isinstance(qty, (int, float)) and qty
                for qty in (total.get(asset), free.get(asset), used.get(asset))
            )
        }
    )
    return {
        "assets": {
            asset: {
                "free": free.get(asset),
                "used": used.get(asset),
                "total": total.get(asset),
            }
            for asset in assets
        },
        "info_keys": sorted(raw.get("info", {}).keys())
        if isinstance(raw.get("info"), dict)
        else [],
    }


def _trim_position(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": raw.get("symbol"),
        "side": raw.get("side"),
        "contracts": raw.get("contracts"),
        "contractSize": raw.get("contractSize"),
        "entryPrice": raw.get("entryPrice"),
        "markPrice": raw.get("markPrice"),
        "notional": raw.get("notional"),
        "leverage": raw.get("leverage"),
        "unrealizedPnl": raw.get("unrealizedPnl"),
        "marginMode": raw.get("marginMode"),
        "hedged": raw.get("hedged"),
        "percentage": raw.get("percentage"),
    }


def _trim_order(
    raw: dict[str, Any],
    *,
    order_kind: str | None = None,
) -> dict[str, Any]:
    info = raw.get("info") if isinstance(raw.get("info"), dict) else {}
    kind = order_kind or _infer_order_kind(info)
    order_type = _resolve_order_type(raw, info, kind)
    close_position = info.get("closePosition")
    if close_position is None:
        close_position = raw.get("closePosition")
    return {
        "id": raw.get("id"),
        "clientOrderId": raw.get("clientOrderId"),
        "symbol": raw.get("symbol"),
        "order_kind": kind,
        "type": order_type,
        "side": raw.get("side"),
        "price": raw.get("price"),
        "amount": raw.get("amount"),
        "filled": raw.get("filled"),
        "remaining": raw.get("remaining"),
        "status": raw.get("status"),
        "reduceOnly": raw.get("reduceOnly"),
        "stopPrice": raw.get("stopPrice")
        if raw.get("stopPrice") is not None
        else raw.get("triggerPrice"),
        "workingType": info.get("workingType"),
        "algoStatus": info.get("algoStatus"),
        "closePosition": close_position,
        "timestamp": raw.get("timestamp"),
    }


def _infer_order_kind(info: dict[str, Any]) -> str:
    algo_type = info.get("algoType")
    if isinstance(algo_type, str) and algo_type.upper() == "CONDITIONAL":
        return "conditional"
    if info.get("algoId") is not None:
        return "conditional"
    return "resting"


def _resolve_order_type(raw: dict[str, Any], info: dict[str, Any], order_kind: str) -> Any:
    if order_kind == "conditional":
        venue_type = info.get("orderType")
        if isinstance(venue_type, str) and venue_type:
            return venue_type.lower()
    return raw.get("type")


fetch_crypto_ohlcv_result = as_call_result(fetch_crypto_ohlcv, map_error=map_ccxt_error)
fetch_crypto_ticker_result = as_call_result(fetch_crypto_ticker, map_error=map_ccxt_error)
fetch_balance_result = as_call_result(fetch_balance, map_error=map_ccxt_error)
fetch_positions_result = as_call_result(fetch_positions, map_error=map_ccxt_error)
fetch_open_orders_result = as_call_result(fetch_open_orders, map_error=map_ccxt_error)
create_order_result = as_call_result(create_order, map_error=map_ccxt_error)
cancel_order_result = as_call_result(cancel_order, map_error=map_ccxt_error)
set_leverage_result = as_call_result(set_leverage, map_error=map_ccxt_error)
set_margin_mode_result = as_call_result(set_margin_mode, map_error=map_ccxt_error)
set_position_mode_result = as_call_result(set_position_mode, map_error=map_ccxt_error)
