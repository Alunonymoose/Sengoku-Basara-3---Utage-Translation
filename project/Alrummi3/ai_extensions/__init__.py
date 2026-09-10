"""Extension points for Alrummi 3 local AI providers."""

from .registry import ExtensionInfo, discover_extensions

__all__ = ["ExtensionInfo", "discover_extensions"]

