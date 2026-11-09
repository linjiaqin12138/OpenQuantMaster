from __future__ import annotations

from abc import ABC


class BaseService(ABC):
    """Public facade of one application capability.

    A service groups the UseCases of a capability and exposes them through
    semantically named methods. It owns the capability configuration and
    delegates each operation to its UseCase, whose ``run()`` is the standard
    action boundary: request validation, execution, response validation, and
    result normalization all live there.
    """
