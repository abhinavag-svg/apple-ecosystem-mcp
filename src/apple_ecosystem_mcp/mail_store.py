from __future__ import annotations

import os
import json
import plistlib
import sqlite3
import shutil
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse


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
SNAPSHOT_TTL_SECONDS = 900
SNAPSHOT_STATE_FILENAME = "snapshot-state.json"
FULL_DISK_ACCESS_SETTINGS = "System Settings > Privacy & Security > Full Disk Access"
MAIL_PREFERENCES_PATH = (
    Path.home()
    / "Library"
    / "Containers"
    / "com.apple.mail"
    / "Data"
    / "Library"
    / "Preferences"
    / "com.apple.mail.plist"
)
ACCOUNTS_DB_PATH = Path.home() / "Library" / "Accounts" / "Accounts4.sqlite"


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


def default_mail_preferences_path() -> Path:
    override = os.environ.get("APPLE_ECOSYSTEM_MCP_MAIL_PREFERENCES")
    if override:
        return Path(override).expanduser()
    return MAIL_PREFERENCES_PATH


def default_accounts_db_path() -> Path:
    override = os.environ.get("APPLE_ECOSYSTEM_MCP_ACCOUNTS_DB")
    if override:
        return Path(override).expanduser()
    return ACCOUNTS_DB_PATH


def _snapshot_root() -> Path:
    override = os.environ.get("APPLE_ECOSYSTEM_MCP_MAIL_SNAPSHOT_ROOT")
    if override:
        return Path(override).expanduser()
    return Path(tempfile.gettempdir()) / "apple-ecosystem-mcp-mail-snapshots"


def _snapshot_state_path() -> Path:
    return _snapshot_root() / SNAPSHOT_STATE_FILENAME


def _mail_store_sibling_paths(path: Path) -> list[Path]:
    return [path, path.with_name(path.name + "-wal"), path.with_name(path.name + "-shm")]


def _cleanup_snapshot_dir(path: Path) -> None:
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        pass


def _load_snapshot_state() -> dict[str, Any] | None:
    state_path = _snapshot_state_path()
    if not state_path.exists():
        return None
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return data


def _write_snapshot_state(data: dict[str, Any]) -> None:
    root = _snapshot_root()
    root.mkdir(parents=True, exist_ok=True)
    _snapshot_state_path().write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def clear_mail_snapshot_state() -> None:
    state = _load_snapshot_state()
    if state and state.get("snapshot_dir"):
        _cleanup_snapshot_dir(Path(str(state["snapshot_dir"])))
    try:
        _snapshot_state_path().unlink()
    except FileNotFoundError:
        pass


def get_mail_snapshot_state(*, include_expired: bool = False) -> dict[str, Any] | None:
    state = _load_snapshot_state()
    if state is None:
        return None
    expires_at = float(state.get("expires_at", 0) or 0)
    now = time.time()
    if expires_at and expires_at < now and not include_expired:
        clear_mail_snapshot_state()
        return None
    snapshot_path = state.get("snapshot_db_path")
    if snapshot_path and not Path(str(snapshot_path)).exists():
        clear_mail_snapshot_state()
        return None
    return state


def refresh_mail_snapshot(*, source_path: Path | None = None, ttl_seconds: int = SNAPSHOT_TTL_SECONDS) -> dict[str, Any]:
    path = source_path or default_envelope_index_path()
    if not path.exists():
        raise MailStoreUnavailable("mail_store_unavailable", "Mail Envelope Index was not found")
    _assert_mail_store_readable(path)

    root = _snapshot_root()
    root.mkdir(parents=True, exist_ok=True)
    previous = get_mail_snapshot_state(include_expired=True)
    if previous and previous.get("snapshot_dir"):
        _cleanup_snapshot_dir(Path(str(previous["snapshot_dir"])))

    snapshot_dir = Path(tempfile.mkdtemp(prefix="snapshot-", dir=root))
    snapshot_db_path = snapshot_dir / "Envelope Index"
    copied: list[str] = []
    try:
        for source in _mail_store_sibling_paths(path):
            if not source.exists():
                continue
            target_name = "Envelope Index" if source == path else source.name
            shutil.copy2(source, snapshot_dir / target_name)
            copied.append(target_name)
    except PermissionError as exc:
        _cleanup_snapshot_dir(snapshot_dir)
        raise MailStoreUnavailable(
            "mail_store_permission_denied",
            "Mail snapshot could not be created because this runtime cannot read Apple Mail data",
        ) from exc
    except OSError as exc:
        _cleanup_snapshot_dir(snapshot_dir)
        raise MailStoreUnavailable("mail_snapshot_unavailable", "Mail snapshot could not be created") from exc

    created_at = time.time()
    state = {
        "snapshot_dir": str(snapshot_dir),
        "snapshot_db_path": str(snapshot_db_path),
        "source_path": str(path),
        "created_at": created_at,
        "expires_at": created_at + max(1, int(ttl_seconds)),
        "ttl_seconds": max(1, int(ttl_seconds)),
        "copied_files": copied,
    }
    _write_snapshot_state(state)
    return state


def search_mail_store(search: MailSearchQuery, *, db_path: Path | None = None) -> list[dict[str, Any]]:
    if not mail_store_enabled():
        raise MailStoreUnavailable("mail_store_disabled", "Local Mail store provider is disabled")

    path = Path(db_path) if db_path else default_envelope_index_path()
    if not path.exists():
        raise MailStoreUnavailable(
            "mail_store_unavailable",
            "Mail Envelope Index was not found",
        )
    _assert_mail_store_readable(path)

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
        return _execute_search(conn, search, account_map=load_mail_account_map())
    except sqlite3.OperationalError as exc:
        raise MailStoreUnavailable(
            "mail_store_query_failed",
            "Mail Envelope Index could not be queried",
        ) from exc
    finally:
        conn.close()


def get_mail_store_message(identifier: str, *, db_path: Path | None = None) -> dict[str, Any] | None:
    if not mail_store_enabled():
        raise MailStoreUnavailable("mail_store_disabled", "Local Mail store provider is disabled")

    path = Path(db_path) if db_path else default_envelope_index_path()
    if not path.exists():
        raise MailStoreUnavailable(
            "mail_store_unavailable",
            "Mail Envelope Index was not found",
        )
    _assert_mail_store_readable(path)

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
        return _execute_get_message(conn, identifier, account_map=load_mail_account_map())
    except sqlite3.OperationalError as exc:
        raise MailStoreUnavailable(
            "mail_store_query_failed",
            "Mail Envelope Index could not be queried",
        ) from exc
    finally:
        conn.close()


def list_mail_store_mailboxes(*, db_path: Path | None = None) -> list[dict[str, Any]]:
    if not mail_store_enabled():
        raise MailStoreUnavailable("mail_store_disabled", "Local Mail store provider is disabled")

    path = Path(db_path) if db_path else default_envelope_index_path()
    if not path.exists():
        raise MailStoreUnavailable(
            "mail_store_unavailable",
            "Mail Envelope Index was not found",
        )
    _assert_mail_store_readable(path)

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
        account_map = load_mail_account_map()
        rows = conn.execute("select ROWID as rowid, url from mailboxes order by ROWID asc").fetchall()
        return [_row_to_mailbox(row, account_map=account_map) for row in rows]
    except sqlite3.OperationalError as exc:
        raise MailStoreUnavailable(
            "mail_store_query_failed",
            "Mail Envelope Index could not be queried",
        ) from exc
    finally:
        conn.close()


def inspect_mail_store(*, db_path: Path | None = None) -> dict[str, Any]:
    path = Path(db_path) if db_path else default_envelope_index_path()
    result: dict[str, Any] = {
        "provider": "mail_store",
        "path": str(path),
        "exists": path.exists(),
        "enabled": mail_store_enabled(),
        "ok": False,
    }
    snapshot_state = get_mail_snapshot_state()
    if snapshot_state is None:
        result["snapshot"] = {"available": False}
    else:
        result["snapshot"] = {
            "available": True,
            "snapshot_db_path": snapshot_state.get("snapshot_db_path"),
            "source_path": snapshot_state.get("source_path"),
            "created_at": snapshot_state.get("created_at"),
            "expires_at": snapshot_state.get("expires_at"),
            "ttl_seconds": snapshot_state.get("ttl_seconds"),
        }

    if not result["enabled"]:
        result["error"] = "mail_store_disabled"
        result["message"] = "Local Mail store provider is disabled"
        return result

    if not path.exists():
        result["error"] = "mail_store_unavailable"
        result["message"] = "Mail Envelope Index was not found"
        return result

    try:
        _assert_mail_store_readable(path)
    except MailStoreUnavailable as exc:
        result.update(exc.to_dict())
        result["next_step"] = "Run apple-ecosystem-mcp mail refresh-snapshot from Terminal or grant Full Disk Access."
        result["settings_path"] = FULL_DISK_ACCESS_SETTINGS
        return result

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
        result["error"] = code
        result["message"] = "Mail Envelope Index could not be opened"
        if code == "mail_store_permission_denied":
            result["next_step"] = (
                "Run apple-ecosystem-mcp mail refresh-snapshot from Terminal or grant Full Disk Access."
            )
            result["settings_path"] = FULL_DISK_ACCESS_SETTINGS
        return result

    try:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("select name from sqlite_master where type='table' order by name").fetchall()
        table_names = [str(row[0]) for row in rows]
        result["table_count"] = len(table_names)
        result["tables"] = table_names
        missing = sorted(REQUIRED_TABLES - set(table_names))
        result["missing_required_tables"] = missing
        if missing:
            result["error"] = "mail_store_unsupported_schema"
            result["message"] = "Mail Envelope Index schema is not supported"
            return result
        latest = conn.execute(
            "select max(date_received) as latest_date_received, count(*) as message_count from messages where deleted = 0"
        ).fetchone()
        result["message_count"] = int(latest["message_count"] or 0)
        result["latest_date_received"] = _format_timestamp(latest["latest_date_received"])
        result["ok"] = True
        return result
    finally:
        conn.close()


def _assert_mail_store_readable(path: Path) -> None:
    try:
        with path.open("rb"):
            return
    except PermissionError as exc:
        raise MailStoreUnavailable(
            "mail_store_permission_denied",
            "Apple Mail data is not readable from this runtime",
        ) from exc


def _validate_schema(conn: sqlite3.Connection) -> None:
    rows = conn.execute("select name from sqlite_master where type='table'").fetchall()
    found = {str(row[0]) for row in rows}
    missing = sorted(REQUIRED_TABLES - found)
    if missing:
        raise MailStoreUnavailable(
            "mail_store_unsupported_schema",
            "Mail Envelope Index schema is not supported",
        )


def _execute_search(
    conn: sqlite3.Connection,
    search: MailSearchQuery,
    *,
    account_map: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
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

    sender_address_expr = (
        "coalesce(snd.address, (select a.address from sender_addresses sa join addresses a on a.ROWID = sa.address "
        "where sa.sender = m.sender order by sa.ROWID asc limit 1), '')"
    )
    sender_comment_expr = (
        "coalesce(snd.comment, (select a.comment from sender_addresses sa join addresses a on a.ROWID = sa.address "
        "where sa.sender = m.sender order by sa.ROWID asc limit 1), '')"
    )
    sender_search_expr = f"({sender_address_expr} || ' ' || {sender_comment_expr})"

    if search.from_addr:
        where.append(
            f"{sender_search_expr} like ? escape '\\' collate nocase"
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
            query_clause.append(f"{sender_search_expr} like ? escape '\\' collate nocase")
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
            {sender_address_expr} as sender_address,
            {sender_comment_expr} as sender_comment,
            mb.ROWID as mailbox_rowid,
            mb.url as mailbox_url,
            g.message_id_header as message_id_header,
            exists (select 1 from attachments att where att.message = m.ROWID) as has_attachments
        from messages m
        left join subjects subj on subj.ROWID = m.subject
        left join addresses snd on snd.ROWID = m.sender
        left join mailboxes mb on mb.ROWID = m.mailbox
        left join message_global_data g on g.message_id = m.message_id
        where {" and ".join(where)}
        order by m.date_received desc, m.ROWID desc
        limit ?
    """
    params.append(search.limit)
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_message(row, account_map=account_map) for row in rows]


def _execute_get_message(
    conn: sqlite3.Connection,
    identifier: str,
    *,
    account_map: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    needle = (identifier or "").strip()
    if not needle:
        raise MailStoreUnavailable("invalid_input", "Message identifier is required", recoverable=False)

    sql = """
        select
            m.ROWID as rowid,
            m.message_id as internal_id,
            m.date_received as date_received,
            m.read as read,
            m.flagged as flagged,
            subj.subject as subject,
            coalesce(
                snd.address,
                (select a.address from sender_addresses sa
                 join addresses a on a.ROWID = sa.address
                 where sa.sender = m.sender
                 order by sa.ROWID asc
                 limit 1),
                ''
            ) as sender_address,
            coalesce(
                snd.comment,
                (select a.comment from sender_addresses sa
                 join addresses a on a.ROWID = sa.address
                 where sa.sender = m.sender
                 order by sa.ROWID asc
                 limit 1),
                ''
            ) as sender_comment,
            mb.ROWID as mailbox_rowid,
            mb.url as mailbox_url,
            g.message_id_header as message_id_header,
            exists (select 1 from attachments att where att.message = m.ROWID) as has_attachments
        from messages m
        left join subjects subj on subj.ROWID = m.subject
        left join addresses snd on snd.ROWID = m.sender
        left join mailboxes mb on mb.ROWID = m.mailbox
        left join message_global_data g on g.message_id = m.message_id
        where m.deleted = 0
          and (
            g.message_id_header = ?
            or cast(m.message_id as text) = ?
            or cast(m.ROWID as text) = ?
          )
        order by
            case
                when g.message_id_header = ? then 0
                when cast(m.message_id as text) = ? then 1
                when cast(m.ROWID as text) = ? then 2
                else 3
            end,
            m.date_received desc,
            m.ROWID desc
        limit 1
    """
    row = conn.execute(sql, (needle, needle, needle, needle, needle, needle)).fetchone()
    if row is None:
        return None
    return _row_to_message(row, account_map=account_map)


def _row_to_message(row: sqlite3.Row, *, account_map: dict[str, str] | None = None) -> dict[str, Any]:
    internal_id = str(row["internal_id"] or row["rowid"])
    mail_object_id = str(row["rowid"] or "")
    message_id = _clean_text(row["message_id_header"]) or internal_id
    mailbox_url = _clean_text(row["mailbox_url"])
    account_token = _mailbox_account_token(mailbox_url)
    sender = _format_sender(_clean_text(row["sender_address"]), _clean_text(row["sender_comment"]))
    return {
        "id": message_id,
        "internal_id": internal_id,
        "mail_object_id": mail_object_id,
        "subject": _clean_text(row["subject"]) or "",
        "sender": sender,
        "date": _format_timestamp(row["date_received"]),
        "preview": "",
        "mailbox_id": mailbox_url or str(row["mailbox_rowid"]),
        "mailbox_path": _mailbox_path(mailbox_url),
        "account_name": _account_name_for_token(account_token, account_map),
        "account_token": account_token,
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


def _mailbox_account_token(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"


def _account_identifier_from_token(token: str | None) -> str | None:
    if not token:
        return None
    parsed = urlparse(token)
    if parsed.netloc:
        return parsed.netloc
    return None


def _add_account_mapping(mapping: dict[str, str], url: Any, name: Any) -> None:
    label = _clean_text(name)
    token = _mailbox_account_token(_clean_text(url))
    if not label or not token:
        return
    mapping.setdefault(token, label)
    identifier = _account_identifier_from_token(token)
    if identifier:
        mapping.setdefault(identifier, label)


def _walk_mail_preferences(obj: Any, mapping: dict[str, str]) -> None:
    if isinstance(obj, dict):
        name = obj.get("MailboxUidName")
        if name:
            _add_account_mapping(mapping, obj.get("MailboxUidAccountURLString"), name)
            _add_account_mapping(mapping, obj.get("MailboxUidPersistentIdentifier"), name)
        for value in obj.values():
            _walk_mail_preferences(value, mapping)
    elif isinstance(obj, list):
        for value in obj:
            _walk_mail_preferences(value, mapping)


def _load_mail_preferences_account_map(path: Path | None = None) -> dict[str, str]:
    preferences_path = Path(path) if path else default_mail_preferences_path()
    try:
        with preferences_path.open("rb") as handle:
            data = plistlib.load(handle)
    except (FileNotFoundError, PermissionError, OSError, plistlib.InvalidFileException):
        return {}
    mapping: dict[str, str] = {}
    _walk_mail_preferences(data, mapping)
    return mapping


def _load_accounts_db_account_map(path: Path | None = None) -> dict[str, str]:
    db_path = Path(path) if path else default_accounts_db_path()
    if not db_path.exists():
        return {}
    try:
        db_uri = f"file:{quote(str(db_path), safe='/')}?mode=ro"
        conn = sqlite3.connect(db_uri, uri=True)
    except sqlite3.Error:
        return {}
    try:
        rows = conn.execute(
            """
            select ZIDENTIFIER as identifier,
                   ZACCOUNTDESCRIPTION as description,
                   ZUSERNAME as username
            from ZACCOUNT
            where ZIDENTIFIER is not null
            """
        ).fetchall()
    except sqlite3.Error:
        return {}
    finally:
        conn.close()

    mapping: dict[str, str] = {}
    for identifier, description, username in rows:
        identifier_text = _clean_text(identifier)
        label = _clean_text(description) or _clean_text(username)
        if not identifier_text or not label:
            continue
        mapping.setdefault(identifier_text, label)
        for scheme in ("imap", "ews", "pop", "local"):
            mapping.setdefault(f"{scheme}://{identifier_text}", label)
    return mapping


def load_mail_account_map(
    *,
    preferences_path: Path | None = None,
    accounts_db_path: Path | None = None,
) -> dict[str, str]:
    """Return deterministic Mail account labels keyed by account URL token."""
    mapping = _load_accounts_db_account_map(accounts_db_path)
    mapping.update(_load_mail_preferences_account_map(preferences_path))
    return mapping


def _account_name_for_token(token: str | None, account_map: dict[str, str] | None = None) -> str | None:
    if not token:
        return None
    mapping = account_map or {}
    direct = mapping.get(token)
    if direct:
        return direct
    identifier = _account_identifier_from_token(token)
    if identifier:
        return mapping.get(identifier)
    return None


def _row_to_mailbox(row: sqlite3.Row, *, account_map: dict[str, str] | None = None) -> dict[str, Any]:
    mailbox_url = _clean_text(row["url"])
    account_token = _mailbox_account_token(mailbox_url)
    return {
        "mailbox_id": mailbox_url or str(row["rowid"]),
        "mailbox_url": mailbox_url,
        "mailbox_path": _mailbox_path(mailbox_url),
        "account_token": account_token,
        "account_name": _account_name_for_token(account_token, account_map),
    }


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
