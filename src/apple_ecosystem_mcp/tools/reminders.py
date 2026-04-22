from __future__ import annotations

from mcp.types import ToolAnnotations

from ..server import mcp


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def reminders_lists() -> list[str]:
    """List all reminder lists."""
    raise NotImplementedError("Phase 3 implementation pending")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def reminders_list(list_name: str | None = None, completed: bool = False) -> list[dict]:
    """List reminders, optionally filtered by list or status."""
    raise NotImplementedError("Phase 3 implementation pending")


@mcp.tool()
def reminders_create(
    title: str,
    list_name: str = "Reminders",
    due: str | None = None,
    notes: str | None = None,
    priority: int = 0,
) -> dict:
    """Create a reminder."""
    raise NotImplementedError("Phase 3 implementation pending")


@mcp.tool()
def reminders_complete(reminder_id: str) -> dict:
    """Mark a reminder as complete."""
    raise NotImplementedError("Phase 3 implementation pending")


@mcp.tool(annotations=ToolAnnotations(destructiveHint=True))
def reminders_delete(reminder_id: str) -> dict:
    """Delete a reminder."""
    raise NotImplementedError("Phase 3 implementation pending")
