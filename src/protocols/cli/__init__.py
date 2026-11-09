from src.protocols.cli.base import main
from src.protocols.cli.commands import register_services

register_services()

__all__ = ["main"]
