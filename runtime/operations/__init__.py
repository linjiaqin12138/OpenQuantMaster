"""Atomic operations — pure algorithms or single API/IO calls. No orchestration."""

from runtime.operations.echo import echo_message

__all__ = ["echo_message"]
