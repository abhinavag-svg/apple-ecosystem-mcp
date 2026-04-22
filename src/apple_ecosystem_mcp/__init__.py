"""Apple Ecosystem MCP server package."""

from __future__ import annotations

__all__ = ["__version__"]

try:
    from importlib.metadata import version as _version

    __version__ = _version("apple-ecosystem-mcp")
except Exception:  # pragma: no cover
    # Package metadata not available when running from source without installation.
    __version__ = "0.0.0"

