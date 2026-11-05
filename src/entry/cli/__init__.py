from src.entry.cli.base import main
from src.entry.cli.services import register_services

register_services()

__all__ = ["main"]
