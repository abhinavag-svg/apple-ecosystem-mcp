from __future__ import annotations

from mcp.types import ToolAnnotations

from ..permissions import ICLOUD_ROOT
from ..server import mcp


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def icloud_list(path: str = "/") -> list[dict]:
    """List files and folders in iCloud Drive."""
    raise NotImplementedError("Phase 5 implementation pending")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def icloud_read(path: str) -> dict:
    """Read a file from iCloud Drive."""
    raise NotImplementedError("Phase 5 implementation pending")


@mcp.tool()
def icloud_write(path: str, content: str, create_dirs: bool = True) -> dict:
    """Write a file to iCloud Drive."""
    raise NotImplementedError("Phase 5 implementation pending")


@mcp.tool()
def icloud_move(src: str, dst: str) -> dict:
    """Move or rename a file in iCloud Drive."""
    raise NotImplementedError("Phase 5 implementation pending")


@mcp.tool(annotations=ToolAnnotations(destructiveHint=True))
def icloud_delete(path: str, confirm: bool = False) -> dict:
    """Delete a file from iCloud Drive (requires confirm=True)."""
    raise NotImplementedError("Phase 5 implementation pending")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def icloud_search(query: str, path: str = "/", content_search: bool = False) -> list[dict]:
    """Search iCloud Drive by filename or content."""
    raise NotImplementedError("Phase 5 implementation pending")


__all__ = ["ICLOUD_ROOT"]
