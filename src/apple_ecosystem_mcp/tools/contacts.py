from __future__ import annotations

from mcp.types import ToolAnnotations

from ..server import mcp


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def contacts_search(query: str, limit: int = 10) -> list[dict]:
    """Search contacts by name, email, phone, or company."""
    raise NotImplementedError("Phase 4 implementation pending")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def contacts_get(contact_id: str) -> dict:
    """Get a full contact record by id."""
    raise NotImplementedError("Phase 4 implementation pending")


@mcp.tool()
def contacts_create(
    first: str,
    last: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    company: str | None = None,
) -> dict:
    """Create a new contact."""
    raise NotImplementedError("Phase 4 implementation pending")


@mcp.tool()
def contacts_update(
    contact_id: str,
    first: str | None = None,
    last: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    company: str | None = None,
) -> dict:
    """Update fields on an existing contact."""
    raise NotImplementedError("Phase 4 implementation pending")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def contacts_list_groups() -> list[str]:
    """List contact groups."""
    raise NotImplementedError("Phase 4 implementation pending")
