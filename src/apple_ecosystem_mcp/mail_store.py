from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote


class MailStoreUnavailable(RuntimeError):
    """Raised when the local Mail metadata store cannot be used."""

    def __init__(self, code: str, message: str, *, recoverable: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.recoverable = recoverable

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.code,
            "message": str(self),
            "recoverable": self.recoverable,
            "provider": "mail_store",
        }


@dataclass(frozen=True)
class MailSearchQuery:
    query: str
    limit: int
    since: str | None = None
    before: str | None = None
    mailbox_id: str | None = None
    mailbox_ids: tuple[str, ...] = ()
    search_subject: bool = True
    search_sender: bool = False
    unread: bool | None = None
    flagged: bool | None = None
    has_attachments: bool | None = None
    from_addr: str | None = None
    to_addr: str | None = None
    cc_addr: str | None = None


REQUIRED_TABLES = {
    "messages",
    "subjects",
    "addresses",
    "mailboxes",
    "message_global_data",
    "attachments",
    "recipients",
}


def mail_store_enabled() -> bool:
    value = os.environ.get("APPLE_ECOSYSTEM_MCP_MAIL_STORE", "1").strip().lower()
    return value not in {"0", "false", "off", "no"}


def default_envelope_index_path() -> Path:
    override = os.environ.get("APPLE_ECOSYSTEM_MCP_MAIL_ENVELOPE_INDEX")
    if override:
        return Path(override).expanduser()

    mail_root = Path.home() / "Library" / "Mail"
    candidates = sorted(mail_root.glob("V*/MailData/Envelope Index"), reverse=True)
    if candidates:
        return candidates[0]
    return mail_root / "V10" / "MailData" / "Envelope Index"


def search_mail_store(search: MailSearchQuery, *, db_path: Path | None = None) -> list[dict[str, Any]]:
    if not mail_store_enabled():
        raise MailStoreUnavailable("mail_store_disabled", "Local Mail store provider is disabled")

    path = db_path or default_envelope_index_path()
    if not path.exists():
        raise MailStoreUnavailable(
            "mail_store_unavailable",
            "Mail Envelope Index was not found",
        )

    try:
        db_uri = f"file:{quote(str(path), safe='/')}?mode=ro"
        conn = sqlite3.connect(db_uri, uri=True)
    except sqlite3.OperationalError as exc:
        message = str(exc).lower()
        code = (
            "mail_store_permission_denied"
            if "permission" in message or "not authorized" in message
            else "mail_store_unavailable"
        )
        raise MailStoreUnavailable(code, "Mail Envelope Index could not be opened") from exc

    try:
        conn.row_factory = sqlite3.Row
        _validate_schema(conn)
        return _execute_search(conn, search)
    except sqlite3.OperationalError as exc:
        raise MailStoreUnavailable(
            "mail_store_query_failed",
            "Mail Envelope Index could not be queried",
        ) from exc
    finally:
        conn.close()


def _validate_schema(conn: sqlite3.Connection) -> None:
    rows = conn.execute("select name from sqlite_master where type='table'").fetchall()
    found = {str(row[0]) for row in rows}
    missing = sorted(REQUIRED_TABLES - found)
    if missing:
        raise MailStoreUnavailable(
            "mail_store_unsupported_schema",
            "Mail Envelope Index schema is not supported",
        )


def _execute_search(conn: sqlite3.Connection, search: MailSearchQuery) -> list[dict[str, Any]]:
    where = ["m.deleted = 0"]
    params: list[Any] = []

    since_ts = _parse_timestamp(search.since)
    if since_ts is not None:
        where.append("m.date_received >= ?")
        params.append(since_ts)

    before_ts = _parse_timestamp(search.before)
    if before_ts is not None:
        where.append("m.date_received <= ?")
        params.append(before_ts)

    mailbox_values = [value for value in (search.mailbox_id, *search.mailbox_ids) if value]
    if mailbox_values:
        mailbox_clause = []
        for value in mailbox_values:
            mailbox_clause.append("cast(m.mailbox as text) = ?")
            params.append(value)
            mailbox_clause.append("mb.url = ?")
            params.append(value)
            mailbox_clause.append("mb.url like ? escape '\\'")
            params.append(f"%/{_escape_like(value)}")
        where.append("(" + " or ".join(mailbox_clause) + ")")

    if search.unread is not None:
        where.append("m.read = ?")
        params.append(0 if search.unread else 1)

    if search.flagged is not None:
        where.append("m.flagged = ?")
        params.append(1 if search.flagged else 0)

    if search.has_attachments is not None:
        op = "exists" if search.has_attachments else "not exists"
        where.append(f"{op} (select 1 from attachments att where att.message = m.ROWID)")

    if search.from_addr:
        where.append(
            "(coalesce(sender_addr.address, '') || ' ' || coalesce(sender_addr.comment, '')) "
            "like ? escape '\\' collate nocase"
        )
        params.append(f"%{_escape_like(search.from_addr)}%")

    if search.to_addr:
        where.append(
            "exists (select 1 from recipients tr join addresses ta on ta.ROWID = tr.address "
            "where tr.message = m.ROWID and tr.type = 0 and "
            "(coalesce(ta.address, '') || ' ' || coalesce(ta.comment, '')) "
            "like ? escape '\\' collate nocase)"
        )
        params.append(f"%{_escape_like(search.to_addr)}%")

    if search.cc_addr:
        where.append(
            "exists (select 1 from recipients cr join addresses ca on ca.ROWID = cr.address "
            "where cr.message = m.ROWID and cr.type = 1 and "
            "(coalesce(ca.address, '') || ' ' || coalesce(ca.comment, '')) "
            "like ? escape '\\' collate nocase)"
        )
        params.append(f"%{_escape_like(search.cc_addr)}%")

    if search.query:
        query_clause = []
        pattern = f"%{_escape_like(search.query)}%"
        if search.search_subject:
            query_clause.append("coalesce(subj.subject, '') like ? escape '\\' collate nocase")
            params.append(pattern)
        if search.search_sender:
            query_clause.append(
                "(coalesce(sender_addr.address, '') || ' ' || coalesce(sender_addr.comment, '')) "
                "like ? escape '\\' collate nocase"
            )
            params.append(pattern)
        if not query_clause:
            return []
        where.append("(" + " or ".join(query_clause) + ")")

    sql = f"""
        select
            m.ROWID as rowid,
            m.message_id as internal_id,
            m.date_received as date_received,
            m.read as read,
            m.flagged as flagged,
            subj.subject as subject,
            sender_addr.address as sender_address,
            sender_addr.comment as sender_comment,
            mb.ROWID as mailbox_rowid,
            mb.url as mailbox_url,
            g.message_id_header as message_id_header,
            exists (select 1 from attachments att where att.message = m.ROWID) as has_attachments
        from messages m
        left join subjects subj on subj.ROWID = m.subject
        left join addresses sender_addr on sender_addr.ROWID = m.sender
        left join mailboxes mb on mb.ROWID = m.mailbox
        left join message_global_data g on g.message_id = m.message_id
        where {" and ".join(where)}
        order by m.date_received desc, m.ROWID desc
        limit ?
    """
    params.append(search.limit)
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_message(row) for row in rows]


def _row_to_message(row: sqlite3.Row) -> dict[str, Any]:
    internal_id = str(row["internal_id"] or row["rowid"])
    message_id = _clean_text(row["message_id_header"]) or internal_id
    mailbox_url = _clean_text(row["mailbox_url"])
    sender = _format_sender(_clean_text(row["sender_address"]), _clean_text(row["sender_comment"]))
    return {
        "id": message_id,
        "internal_id": internal_id,
        "subject": _clean_text(row["subject"]) or "",
        "sender": sender,
        "date": _format_timestamp(row["date_received"]),
        "preview": "",
        "mailbox_id": mailbox_url or str(row["mailbox_rowid"]),
        "mailbox_path": _mailbox_path(mailbox_url),
        "account_name": None,
        "has_attachments": bool(row["has_attachments"]),
        "provider": "mail_store",
    }


def _parse_timestamp(value: str | None) -> int | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise MailStoreUnavailable(
            "invalid_input",
            "Invalid ISO 8601 date",
            recoverable=False,
        ) from exc
    return int(parsed.timestamp())


def _format_timestamp(value: Any) -> str:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return ""
    return datetime.fromtimestamp(timestamp).isoformat(timespec="seconds")


def _format_sender(address: str | None, comment: str | None) -> str:
    if address and comment:
        return f"{comment} <{address}>"
    return address or comment or ""


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _mailbox_path(url: str | None) -> str | None:
    if not url:
        return None
    tail = url.rsplit("/", 1)[-1]
    return unquote(tail) if tail else None


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
