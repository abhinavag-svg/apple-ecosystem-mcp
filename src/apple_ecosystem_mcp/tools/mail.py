from __future__ import annotations

from mcp.types import ToolAnnotations

from ..server import mcp


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def mail_search(query: str, mailbox_id: str | None = None, limit: int = 20, since: str | None = None) -> list[dict]:
    """Search Mail messages."""
    raise NotImplementedError("Phase 2 implementation pending")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def mail_get_thread(message_id: str, include_body: bool = True) -> dict:
    """Fetch a message thread by canonical message id."""
    raise NotImplementedError("Phase 2 implementation pending")


@mcp.tool()
def mail_send(
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    reply_to_id: str | None = None,
    from_account: str | None = None,
    dry_run: bool = True,
) -> dict:
    """Compose and send an email (supports dry_run)."""
    raise NotImplementedError("Phase 2 implementation pending")


@mcp.tool()
def mail_create_draft(to: list[str], subject: str, body: str, from_account: str | None = None) -> dict:
    """Create a draft email without sending."""
    raise NotImplementedError("Phase 2 implementation pending")


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def mail_list_mailboxes() -> list[dict]:
    """List mailboxes across all accounts."""
    raise NotImplementedError("Phase 2 implementation pending")


@mcp.tool()
def mail_move_message(message_id: str, mailbox: str) -> dict:
    """Move a message to a mailbox by persistent id."""
    raise NotImplementedError("Phase 2 implementation pending")


@mcp.tool()
def mail_flag_message(message_id: str, flagged: bool) -> dict:
    """Flag or unflag a message."""
    raise NotImplementedError("Phase 2 implementation pending")
