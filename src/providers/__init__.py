"""Concrete, stateless third-party calls.

Each module wraps one external system: HTTP endpoints, exchange SDKs, and
market-data SDKs. Providers own transport details, keep endpoints inside the
module, and expose a throwing form plus a ``Result``-returning variant.
"""
