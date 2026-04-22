from __future__ import annotations

from mcp.types import ToolAnnotations

from ..server import mcp


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def calendar_list_calendars() -> list[dict]:
    """List calendars across all accounts."""
    raise NotImplementedError("Phase 3 implementation pending")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def calendar_list_events(start: str, end: str, calendar_uid: str | None = None) -> list[dict]:
    """List calendar events in a time range."""
    raise NotImplementedError("Phase 3 implementation pending")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def calendar_get_event(event_id: str) -> dict:
    """Get details for a specific event by id."""
    raise NotImplementedError("Phase 3 implementation pending")


@mcp.tool()
def calendar_create_event(
    title: str,
    start: str,
    end: str,
    calendar_uid: str | None = None,
    location: str | None = None,
    notes: str | None = None,
    invitees: list[str] | None = None,
) -> dict:
    """Create a calendar event."""
    raise NotImplementedError("Phase 3 implementation pending")


@mcp.tool()
def calendar_update_event(
    event_id: str,
    title: str | None = None,
    start: str | None = None,
    end: str | None = None,
    location: str | None = None,
    notes: str | None = None,
    invitees: list[str] | None = None,
) -> dict:
    """Update an existing calendar event by id."""
    raise NotImplementedError("Phase 3 implementation pending")


@mcp.tool(annotations=ToolAnnotations(destructiveHint=True))
def calendar_delete_event(event_id: str, confirm: bool = False) -> dict:
    """Delete an event (requires confirm=True)."""
    raise NotImplementedError("Phase 3 implementation pending")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def calendar_find_free_time(
    date: str,
    duration_minutes: int,
    working_hours_start: int = 9,
    working_hours_end: int = 18,
) -> list[dict]:
    """Find available time slots on a date."""
    raise NotImplementedError("Phase 3 implementation pending")
