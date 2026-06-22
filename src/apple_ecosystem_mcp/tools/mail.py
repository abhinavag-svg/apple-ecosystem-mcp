from __future__ import annotations

import json
import re
import subprocess
from typing import Any
from urllib.parse import quote

from mcp.types import ToolAnnotations

from ..bridge import run_applescript, cache_inventory
from ..mail_store import (
    MailStoreUnavailable,
    get_mail_snapshot_state,
    get_mail_store_message,
    inspect_mail_store,
    list_mail_store_mailboxes as store_list_mailboxes,
    read_mail_store_message_body,
    read_mail_store_message_body_by_message_id,
    refresh_mail_snapshot as store_refresh_mail_snapshot,
)
from ..mail_service import (
    MAIL_SEARCH_DEFAULT,
    _SEARCH_SCRIPT,
    _mail_store_mailboxes_by_account,
    _store_only_mailboxes_by_account,
    recent_mail as service_recent_mail,
    search_mail as service_search_mail,
)
from ..preferences import PreferencesStore
from ..prompt_contract import tool_contract
from ..resolver import ResolverError, resolve_target
from ..server import mcp
from .actions import (
    open_app_next_action,
    open_url_next_action,
    terminal_command_next_action,
    tool_next_action,
)

# Result-size policy per CLAUDE.md
_MAIL_BODY_MAX_CHARS = 8_000
_MAIL_PREVIEW_CHARS = 200
_FULL_DISK_ACCESS_SETTINGS_URL = "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"


def _parse_json(raw: str) -> Any:
    """Parse AppleScript JSON output; raise RuntimeError on malformed payload."""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Malformed AppleScript JSON output: {e.msg}") from e


def _nn(value):
    if value is None:
        return None
    if isinstance(value, str) and (value == "" or value == "missing value"):
        return None
    return value


def _normalize_optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"", "null", "missing value"}:
            return None
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    return bool(value)


def _coerce_limit(value: int | str, *, default: int = MAIL_SEARCH_DEFAULT) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit must be an integer") from exc


def _coerce_search_fields(value: list[str] | str | None) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text[0] in "[{":
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ValueError("search_fields must be a list or JSON list string") from exc
            if isinstance(parsed, list):
                return [str(item) for item in parsed if str(item).strip()]
            if isinstance(parsed, str):
                return [parsed]
            raise ValueError("search_fields JSON must decode to a list")
        return [item.strip() for item in text.split(",") if item.strip()]
    raise ValueError("search_fields must be a list or string")


def _coerce_filters(value: dict | str | None) -> dict | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("filters must be an object or JSON object string") from exc
        if isinstance(parsed, dict):
            return parsed
    raise ValueError("filters must be an object or JSON object string")


def _coerce_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "missing value"}:
        return None
    return text


def _tool_next_action(tool: str, arguments: dict[str, Any], *, label: str) -> dict[str, Any]:
    return tool_next_action(tool, arguments, label=label)


def _open_url_next_action(url: str, *, label: str) -> dict[str, Any]:
    return open_url_next_action(url, label=label)


def _open_mail_app_next_action(*, label: str = "Open Mail") -> dict[str, Any]:
    return open_app_next_action("Mail", label=label)


def _terminal_command_next_action(command: str, *, label: str) -> dict[str, Any]:
    return terminal_command_next_action(command, label=label)


def _message_open_url_from_id(message_id: Any) -> str | None:
    text = _coerce_optional_text(message_id)
    if not text or "@" not in text:
        return None
    return _mail_message_url(text)


def _add_message_actions(row: dict[str, Any]) -> dict[str, Any]:
    message_id = row.get("id") or row.get("message_id")
    if not message_id:
        return row
    row.setdefault(
        "next_action",
        _tool_next_action(
            "mail_get_thread",
            {"message_id": str(message_id), "include_body": True},
            label="Read email content",
        ),
    )
    open_url = _message_open_url_from_id(message_id)
    if open_url:
        row.setdefault("open_url", open_url)
        row.setdefault("open_action", _open_url_next_action(open_url, label="Open in Mail"))
    return row


def _add_message_actions_to_rows(rows: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for row in rows:
        if isinstance(row, dict) and not row.get("error"):
            normalized.append(_add_message_actions(dict(row)))
        else:
            normalized.append(row)
    return normalized


def _store_body_payload(scoped: dict[str, Any] | None, *, message_id: str | None = None) -> dict[str, Any] | None:
    try:
        if scoped:
            fallback = read_mail_store_message_body(scoped)
        elif message_id:
            fallback = read_mail_store_message_body_by_message_id(message_id)
        else:
            fallback = None
    except MailStoreUnavailable:
        return None
    if not fallback:
        return None
    body = _truncate_body(_strip_html_and_base64(str(fallback.get("body") or "")))
    if not body:
        return None
    payload = {
        "body": body,
        "body_available": True,
        "body_source": fallback.get("body_source") or "mail_store_emlx",
    }
    for key in ("id", "message_id", "subject", "sender", "date"):
        if fallback.get(key):
            payload.setdefault(key, fallback[key])
    if fallback.get("body_content_type"):
        payload["body_content_type"] = fallback["body_content_type"]
    return payload


def _apply_store_body_fallback(
    data: dict[str, Any],
    scoped: dict[str, Any] | None,
    reason: str,
    *,
    message_id: str | None = None,
) -> bool:
    payload = _store_body_payload(scoped, message_id=message_id)
    if not payload:
        return False
    for key, value in payload.items():
        if key in {"id", "message_id", "subject", "sender", "date"}:
            data.setdefault(key, value)
        else:
            data[key] = value
    data["body_fallback_reason"] = reason
    data.pop("body_unavailable", None)
    return True


def _degraded_thread_result(
    message_id: str,
    reason: str,
    *,
    scoped: dict[str, Any] | None = None,
    include_body: bool = True,
) -> dict[str, Any]:
    result: dict[str, Any] = dict(scoped or {})
    result.setdefault("id", message_id)
    result.setdefault("message_id", message_id)
    result["attachments"] = []
    if include_body:
        if not _apply_store_body_fallback(result, scoped, reason, message_id=message_id):
            result["body"] = ""
            result["body_available"] = False
            result["body_unavailable"] = reason
    else:
        result.pop("body", None)

    open_url = _message_open_url_from_id(message_id)
    if open_url:
        result.setdefault("open_url", open_url)
        result.setdefault("open_action", _open_url_next_action(open_url, label="Open in Mail"))
        result.setdefault("next_action", _open_url_next_action(open_url, label="Open in Mail"))
    else:
        result.setdefault(
            "next_action",
            _tool_next_action(
                "mail_open_message",
                {"message_id": message_id},
                label="Open in Mail",
            ),
        )
    return result


_HTML_TAG_RE = re.compile(r"<[^>]+>")
# Match long runs of base64 alphabet that include at least one upper, one
# lower, and one digit — avoids false positives on long runs of a single
# character (plain text is frequently repetitive, real base64 is not).
_BASE64_BLOCK_RE = re.compile(
    r"(?=[A-Za-z0-9+/=]{200,})"
    r"(?=[^A-Z]*[A-Z])"
    r"(?=[^a-z]*[a-z])"
    r"(?=[^0-9]*[0-9])"
    r"[A-Za-z0-9+/=]{200,}"
)
_WHITESPACE_RE = re.compile(r"\s+")


def _strip_html_and_base64(text: str) -> str:
    """Remove HTML tags and long base64-ish blocks; collapse whitespace."""
    cleaned = _HTML_TAG_RE.sub(" ", text)
    cleaned = _BASE64_BLOCK_RE.sub(" ", cleaned)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned)
    return cleaned.strip()


def _truncate_body(body: str, limit: int = _MAIL_BODY_MAX_CHARS) -> str:
    """Truncate body with a visible marker if above limit."""
    if len(body) <= limit:
        return body
    omitted = len(body) - limit
    return body[:limit] + f"\n[truncated — {omitted} chars omitted]"


def _mail_thread_store_record(message_id: str) -> dict[str, Any] | None:
    try:
        row = get_mail_store_message(message_id)
        if row is not None:
            return row
    except MailStoreUnavailable:
        pass

    snapshot = get_mail_snapshot_state()
    if not snapshot:
        return None
    snapshot_db_path = snapshot.get("snapshot_db_path")
    if not snapshot_db_path:
        return None
    try:
        return get_mail_store_message(message_id, db_path=snapshot_db_path)
    except MailStoreUnavailable:
        return None


def _account_name_for_store_mailbox(mailbox_id: str, mailbox_inventory: list[dict[str, Any]]) -> str | None:
    store_groups = _mail_store_mailboxes_by_account(mailbox_inventory)
    if not store_groups:
        store_groups = _store_only_mailboxes_by_account()
    for account, rows in store_groups.items():
        for row in rows:
            if str(row.get("mailbox_url") or "") == mailbox_id:
                return account
    return None


def _thread_scope_from_store(message_id: str) -> dict[str, Any] | None:
    row = _mail_thread_store_record(message_id)
    if not row:
        return None

    try:
        mailbox_inventory = mail_list_mailboxes()
    except RuntimeError:
        mailbox_inventory = []
    account_name = row.get("account_name") or _account_name_for_store_mailbox(
        str(row.get("mailbox_id") or ""),
        mailbox_inventory,
    )
    if account_name:
        row["account_name"] = account_name
    return row


# ---------------------------------------------------------------------------
# mail_list_mailboxes
# ---------------------------------------------------------------------------

_LIST_MAILBOXES_SCRIPT = r"""
on run argv
    set output to "["
    set firstItem to true
    tell application "Mail"
        set acctCount to count of accounts
        repeat with acctIdx from 1 to acctCount
            set acct to item acctIdx of every account
            set acctName to name of acct
            set mbCount to count of mailboxes of acct
            repeat with mbIdx from 1 to mbCount
                set mb to item mbIdx of every mailbox of acct
                if not firstItem then set output to output & ","
                set firstItem to false
                set mbName to name of mb
                set mbId to ""
                try
                    set mbId to id of mb as text
                end try
                if mbId is "" then
                    set mbId to mbName
                end if
                set mbPath to my buildMailboxPath(mb)
                set mbWritable to missing value
                try
                    set mbWritable to writable of mb
                end try
                set writableStr to "null"
                if mbWritable is true then
                    set writableStr to "true"
                else if mbWritable is false then
                    set writableStr to "false"
                end if
                set output to output & "{\"name\":" & my jsonString(mbName) & ",\"id\":" & my jsonString(mbId) & ",\"account_name\":" & my jsonString(acctName) & ",\"path\":" & my jsonString(mbPath) & ",\"writable\":" & writableStr & "}"
            end repeat
        end repeat
    end tell
    return output & "]"
end run

on buildMailboxPath(mb)
    set pathItems to {}
    set currentMb to mb
    tell application "Mail"
        repeat 100 times
            try
                set mbName to name of currentMb
                set beginning of pathItems to mbName
                set containerMb to container of currentMb
                if containerMb is missing value then
                    exit repeat
                end if
                set currentMb to containerMb
            on error
                exit repeat
            end try
        end repeat
    end tell
    set AppleScript's text item delimiters to "/"
    set pathStr to pathItems as text
    set AppleScript's text item delimiters to ""
    return pathStr
end buildMailboxPath

on jsonString(s)
    if s is missing value then return "null"
    set t to s as string
    set AppleScript's text item delimiters to "\\"
    set parts to text items of t
    set AppleScript's text item delimiters to "\\\\"
    set t to parts as string
    set AppleScript's text item delimiters to "\""
    set parts to text items of t
    set AppleScript's text item delimiters to "\\\""
    set t to parts as string
    set AppleScript's text item delimiters to return
    set parts to text items of t
    set AppleScript's text item delimiters to "\\n"
    set t to parts as string
    set AppleScript's text item delimiters to linefeed
    set parts to text items of t
    set AppleScript's text item delimiters to "\\n"
    set t to parts as string
    set AppleScript's text item delimiters to tab
    set parts to text items of t
    set AppleScript's text item delimiters to "\\t"
    set t to parts as string
    set AppleScript's text item delimiters to ""
    return "\"" & t & "\""
end jsonString
"""


@mcp.tool(annotations=ToolAnnotations(title="List Mailboxes", readOnlyHint=True))
@cache_inventory("mail_mailboxes", ttl=30)
def mail_list_mailboxes() -> list[dict]:
    """List all mailboxes across every Mail account with canonical ids."""
    try:
        store_rows = store_list_mailboxes()
    except MailStoreUnavailable:
        store_rows = []
    if store_rows:
        normalized: list[dict] = []
        for row in store_rows:
            path = _nn(row.get("mailbox_path"))
            mailbox_id = _nn(row.get("mailbox_url")) or _nn(row.get("mailbox_id"))
            name = str(path).rsplit("/", 1)[-1] if path else mailbox_id
            item = {
                "id": mailbox_id,
                "name": name,
                "kind": "mailbox",
                "account_name": _nn(row.get("account_name")),
                "path": path,
                "writable": None,
                "default_candidate": bool(path and str(path).casefold() == "inbox"),
                "provider": "mail_store",
                "account_token": _nn(row.get("account_token")),
            }
            normalized.append(item)
        return normalized

    return _mail_list_mailboxes_applescript()


def _mail_list_mailboxes_applescript() -> list[dict]:
    raw = run_applescript(_LIST_MAILBOXES_SCRIPT)
    data = _parse_json(raw) or []
    if not isinstance(data, list):
        raise RuntimeError("Unexpected mail_list_mailboxes payload shape")
    normalized: list[dict] = []
    for row in data:
        if not isinstance(row, dict):
            continue
        name = _nn(row.get("name"))
        path = _nn(row.get("path"))
        item = {
            "id": _nn(row.get("id")),
            "name": name,
            "kind": "mailbox",
            "account_name": _nn(row.get("account_name")),
            "path": path,
            "writable": _normalize_optional_bool(row.get("writable")),
            "default_candidate": False,
        }
        if name and str(name).casefold() == "inbox":
            item["default_candidate"] = True
        elif path and str(path).casefold() == "inbox":
            item["default_candidate"] = True
        normalized.append(item)
    return normalized


@mcp.tool(
    description=tool_contract("mail_search").description,
    annotations=ToolAnnotations(title=tool_contract("mail_search").title, readOnlyHint=True),
)
def mail_search(
    query: str,
    mailbox_id: str | None = None,
    limit: int | str = MAIL_SEARCH_DEFAULT,
    since: str | None = None,
    before: str | None = None,
    search_fields: list[str] | str | None = None,
    filters: dict | str | None = None,
) -> list[dict]:
    """Search Mail by literal query text or explicit fielded filters."""
    rows = service_search_mail(
        str(query or ""),
        mailbox_id=_coerce_optional_text(mailbox_id),
        limit=_coerce_limit(limit),
        since=_coerce_optional_text(since),
        before=_coerce_optional_text(before),
        search_fields=_coerce_search_fields(search_fields),
        filters=_coerce_filters(filters),
        mailbox_inventory_fn=mail_list_mailboxes,
    )
    return _add_message_actions_to_rows(rows)


@mcp.tool(
    description=tool_contract("mail_recent").description,
    annotations=ToolAnnotations(title=tool_contract("mail_recent").title, readOnlyHint=True),
)
def mail_recent(
    limit: int | str = MAIL_SEARCH_DEFAULT,
    since: str | None = None,
    before: str | None = None,
    mailbox_id: str | None = None,
    filters: dict | str | None = None,
) -> list[dict]:
    """Return the most recent Mail messages in chronological order."""
    rows = service_recent_mail(
        mailbox_id=_coerce_optional_text(mailbox_id),
        limit=_coerce_limit(limit),
        since=_coerce_optional_text(since),
        before=_coerce_optional_text(before),
        filters=_coerce_filters(filters),
        mailbox_inventory_fn=mail_list_mailboxes,
    )
    return _add_message_actions_to_rows(rows)


@mcp.tool(
    annotations=ToolAnnotations(title="Mail Diagnostics", readOnlyHint=True),
)
def mail_diagnostics() -> dict:
    """Inspect local Apple Mail store availability and access state."""
    result = inspect_mail_store()
    if not result.get("ok"):
        result.setdefault(
            "next_action",
            _tool_next_action("mail_access_setup", {}, label="Show Mail access options"),
        )
    return result


@mcp.tool(annotations=ToolAnnotations(title="Mail Access Setup"))
def mail_access_setup(open_settings: bool = False) -> dict:
    """Explain Mail access modes and optionally open Full Disk Access settings."""
    diagnostics = inspect_mail_store()
    local_ok = bool(diagnostics.get("ok"))
    result: dict[str, Any] = {
        "ok": True,
        "local_store_access": "available" if local_ok else "unavailable",
        "diagnostics": diagnostics,
        "recommended_default": "applescript_first_auto",
        "modes": [
            {
                "mode": "auto",
                "description": "Try Mail.app AppleScript first; if AppleScript fails, fall back to local Mail store when available.",
                "requires_full_disk_access": False,
                "tool_filter": {"provider": "auto"},
            },
            {
                "mode": "applescript",
                "description": "Use Mail.app Automation only. No Full Disk Access, but chronological and large-mailbox reads are less reliable.",
                "requires_full_disk_access": False,
                "tool_filter": {"provider": "applescript"},
            },
            {
                "mode": "local",
                "description": "Use the local Mail metadata store for deterministic chronological/account-scoped reads.",
                "requires_full_disk_access": True,
                "tool_filter": {"provider": "local"},
            },
        ],
        "next_steps": [
            "Use normal Mail prompts for AppleScript-first auto mode.",
            "If you do not want Full Disk Access, ask Claude to use AppleScript-only Mail mode.",
            "If you want deterministic local-store reads, grant Full Disk Access to Claude or create a temporary snapshot from Terminal.",
        ],
        "settings_path": "System Settings > Privacy & Security > Full Disk Access",
        "settings_url": _FULL_DISK_ACCESS_SETTINGS_URL,
        "open_url": _FULL_DISK_ACCESS_SETTINGS_URL,
        "next_action": _open_url_next_action(
            _FULL_DISK_ACCESS_SETTINGS_URL,
            label="Open Full Disk Access settings",
        ),
    }
    if open_settings:
        try:
            subprocess.run(["open", _FULL_DISK_ACCESS_SETTINGS_URL], check=True, timeout=5)
            result["settings_opened"] = True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
            result["settings_opened"] = False
            result["settings_error"] = str(exc)
    return result


@mcp.tool(annotations=ToolAnnotations(title="Refresh Mail Snapshot"))
def refresh_mail_snapshot(ttl_seconds: int = 900) -> dict:
    """Create a temporary Mail metadata snapshot for fallback read workflows."""
    try:
        snapshot = store_refresh_mail_snapshot(ttl_seconds=ttl_seconds)
    except MailStoreUnavailable as exc:
        payload = exc.to_dict()
        if exc.code == "mail_store_permission_denied":
            payload["next_step"] = (
                "Run apple-ecosystem-mcp mail refresh-snapshot from Terminal, or grant Full Disk Access to the installed runtime."
            )
            payload["settings_path"] = "System Settings > Privacy & Security > Full Disk Access"
            payload["open_url"] = _FULL_DISK_ACCESS_SETTINGS_URL
            payload["next_action"] = _terminal_command_next_action(
                "apple-ecosystem-mcp mail refresh-snapshot --json",
                label="Create Mail snapshot from Terminal",
            )
        return payload
    return {
        "ok": True,
        "provider": "mail_store_snapshot",
        "source_path": snapshot["source_path"],
        "snapshot_db_path": snapshot["snapshot_db_path"],
        "created_at": snapshot["created_at"],
        "expires_at": snapshot["expires_at"],
        "ttl_seconds": snapshot["ttl_seconds"],
        "copied_files": snapshot["copied_files"],
        "next_action": _tool_next_action(
            "mail_recent",
            {"limit": 20},
            label="Read recent Mail with snapshot fallback",
        ),
    }


# ---------------------------------------------------------------------------
# mail_get_thread
# ---------------------------------------------------------------------------

_GET_THREAD_SCRIPT = r"""
on run argv
    set mid to my normalizeMessageId(item 1 of argv)
    set includeBody to (item 2 of argv) is "1"
    set internalId to item 3 of argv
    set scopedAccount to item 4 of argv
    set scopedMailbox to item 5 of argv

    tell application "Mail"
        set target to missing value
        set mbId to ""
        set acctName to ""
        if scopedAccount is not "" or scopedMailbox is not "" then
            repeat with acct in accounts
                if scopedAccount is "" or (name of acct as string) is scopedAccount then
                    repeat with mb in mailboxes of acct
                        if scopedMailbox is "" or (name of mb as string) is scopedMailbox then
                            set candidates to my findCandidates(mb, internalId, mid)
                            if (count of candidates) > 0 then
                                set target to item 1 of candidates
                                set mbId to my mailboxIdentifier(mb)
                                set acctName to name of acct
                                exit repeat
                            end if
                        end if
                    end repeat
                    if target is not missing value then exit repeat
                end if
            end repeat
        end if

        if target is missing value then
            repeat with acct in accounts
                repeat with mb in mailboxes of acct
                    set candidates to my findCandidates(mb, internalId, mid)
                    if (count of candidates) > 0 then
                        set target to item 1 of candidates
                        set mbId to my mailboxIdentifier(mb)
                        set acctName to name of acct
                        exit repeat
                    end if
                end repeat
                if target is not missing value then exit repeat
            end repeat
        end if

        if target is missing value then
            error "Message not found" number 404
        end if

        set subj to subject of target
        set snd to sender of target
        set dte to (date received of target) as «class isot» as string
        set bodyText to ""
        if includeBody then
            try
                set bodyText to content of target
            end try
        end if

        set atts to "["
        set firstAtt to true
        try
            repeat with a in mail attachments of target
                if not firstAtt then set atts to atts & ","
                set firstAtt to false
                set aName to name of a
                set aSize to file size of a
                set aType to ""
                try
                    set aType to mime type of a
                end try
                set atts to atts & "{\"name\":" & my jsonString(aName) & ",\"size_bytes\":" & (aSize as string) & ",\"mime_type\":" & my jsonString(aType) & "}"
            end repeat
        end try
        set atts to atts & "]"

        set bodyField to ""
        if includeBody then
            set bodyField to ",\"body\":" & my jsonString(bodyText)
        end if

        return "{\"id\":" & my jsonString(mid) & ",\"subject\":" & my jsonString(subj) & ",\"sender\":" & my jsonString(snd) & ",\"date\":" & my jsonString(dte) & ",\"mailbox_id\":" & my jsonString(mbId) & ",\"account_name\":" & my jsonString(acctName) & ",\"attachments\":" & atts & bodyField & "}"
    end tell
end run

on findCandidates(mb, internalId, mid)
    set candidates to {}
    try
        set msgList to messages of mb
    on error
        return candidates
    end try

    repeat with msg in msgList
        if internalId is not "" then
            try
                set msgInternalId to (id of msg) as string
                if msgInternalId is internalId then
                    return {msg}
                end if
            end try
        end if
        try
            set msgMessageId to ""
            tell application "Mail" to set msgMessageId to (message id of msg) as string
            if my normalizeMessageId(msgMessageId) is mid then
                return {msg}
            end if
        end try
        if mid is not "" then
            try
                set msgInternalId to (id of msg) as string
                if msgInternalId is mid then
                    return {msg}
                end if
            end try
        end if
    end repeat
    return candidates
end findCandidates

on normalizeMessageId(valueText)
    set t to valueText as string
    if t starts with "<" then set t to text 2 thru -1 of t
    if t ends with ">" then set t to text 1 thru -2 of t
    return t
end normalizeMessageId

on mailboxIdentifier(mb)
    set mbId to ""
    tell application "Mail"
        try
            set mbId to id of mb as text
        end try
        if mbId is "" then
            try
                set mbId to name of mb as string
            end try
        end if
    end tell
    return mbId
end mailboxIdentifier

on jsonString(s)
    if s is missing value then return "null"
    set t to s as string
    set AppleScript's text item delimiters to "\\"
    set parts to text items of t
    set AppleScript's text item delimiters to "\\\\"
    set t to parts as string
    set AppleScript's text item delimiters to "\""
    set parts to text items of t
    set AppleScript's text item delimiters to "\\\""
    set t to parts as string
    set AppleScript's text item delimiters to return
    set parts to text items of t
    set AppleScript's text item delimiters to "\\n"
    set t to parts as string
    set AppleScript's text item delimiters to linefeed
    set parts to text items of t
    set AppleScript's text item delimiters to "\\n"
    set t to parts as string
    set AppleScript's text item delimiters to tab
    set parts to text items of t
    set AppleScript's text item delimiters to "\\t"
    set t to parts as string
    set AppleScript's text item delimiters to ""
    return "\"" & t & "\""
end jsonString
"""


@mcp.tool(annotations=ToolAnnotations(title="Get Email Thread", readOnlyHint=True))
def mail_get_thread(message_id: str, include_body: bool = True) -> dict:
    """Fetch a Mail message by canonical RFC Message-ID; plain-text body only, 8K cap."""
    scoped = _thread_scope_from_store(message_id)
    if scoped and not include_body:
        scoped = dict(scoped)
        scoped.pop("body", None)
        scoped["attachments"] = []
        return scoped

    internal_id = ""
    scoped_account = ""
    scoped_mailbox = ""
    if scoped:
        internal_id = str(scoped.get("mail_object_id") or scoped.get("internal_id") or "")
        scoped_account = str(scoped.get("account_name") or "")
        scoped_mailbox = str(scoped.get("mailbox_path") or "")

    try:
        raw = run_applescript(
            _GET_THREAD_SCRIPT,
            message_id,
            "1" if include_body else "0",
            internal_id,
            scoped_account,
            scoped_mailbox,
            timeout=15,
        )
    except RuntimeError as exc:
        return _degraded_thread_result(
            message_id,
            str(exc),
            scoped=scoped,
            include_body=include_body,
        )
    data = _parse_json(raw)
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected mail_get_thread payload shape")

    if scoped:
        scoped_expected_account = str(scoped.get("account_name") or "")
        returned_account = str(data.get("account_name") or "")
        if scoped_expected_account and returned_account and returned_account != scoped_expected_account:
            return _degraded_thread_result(
                message_id,
                "Scoped AppleScript read returned a different account "
                f"({returned_account}) than the Mail store record ({scoped_expected_account})",
                scoped=scoped,
                include_body=include_body,
            )
        if not data.get("mailbox_id"):
            data["mailbox_id"] = scoped.get("mailbox_id", "")
        if not data.get("account_name"):
            data["account_name"] = scoped.get("account_name")
        if scoped.get("internal_id") and not data.get("internal_id"):
            data["internal_id"] = scoped["internal_id"]

    if include_body:
        body = data.get("body", "") or ""
        body = _strip_html_and_base64(body)
        data["body"] = _truncate_body(body)
        if data["body"]:
            data["body_available"] = True
        elif not _apply_store_body_fallback(
            data,
            scoped,
            "AppleScript returned an empty body",
            message_id=message_id,
        ):
            data["body_available"] = False
            data["body_unavailable"] = "AppleScript returned an empty body"
    else:
        data.pop("body", None)

    if "attachments" not in data or not isinstance(data["attachments"], list):
        data["attachments"] = []

    return data


# ---------------------------------------------------------------------------
# mail_send / mail_create_draft
# ---------------------------------------------------------------------------

_SEND_SCRIPT = r"""
on run argv
    set subj to item 1 of argv
    set bodyText to item 2 of argv
    set fromAccount to item 3 of argv
    set sendFlag to (item 4 of argv) is "1"
    set toCount to (item 5 of argv) as integer
    set ccCount to (item 6 of argv) as integer

    set toList to {}
    set ccList to {}
    set idx to 7
    repeat toCount times
        set end of toList to item idx of argv
        set idx to idx + 1
    end repeat
    repeat ccCount times
        set end of ccList to item idx of argv
        set idx to idx + 1
    end repeat

    tell application "Mail"
        if fromAccount is not "" then
            set msg to make new outgoing message with properties {subject:subj, content:bodyText, visible:(not sendFlag), sender:fromAccount}
        else
            set msg to make new outgoing message with properties {subject:subj, content:bodyText, visible:(not sendFlag)}
        end if
        tell msg
            repeat with addr in toList
                make new to recipient at end of to recipients with properties {address:addr}
            end repeat
            repeat with addr in ccList
                make new cc recipient at end of cc recipients with properties {address:addr}
            end repeat
        end tell
        if sendFlag then
            send msg
            set mid to ""
            try
                set mid to message id of msg
            end try
            return "{\"success\":true,\"message_id\":" & my jsonString(mid) & "}"
        else
            activate
            set draftId to ""
            try
                set draftId to id of msg as string
            end try
            return "{\"success\":true,\"draft_created\":true,\"draft_visible\":true,\"draft_id\":" & my jsonString(draftId) & ",\"open_mail\":{\"app\":\"Mail\",\"action\":\"activate\",\"already_open\":true}}"
        end if
    end tell
end run

on jsonString(s)
    if s is missing value then return "null"
    set t to s as string
    set AppleScript's text item delimiters to "\\"
    set parts to text items of t
    set AppleScript's text item delimiters to "\\\\"
    set t to parts as string
    set AppleScript's text item delimiters to "\""
    set parts to text items of t
    set AppleScript's text item delimiters to "\\\""
    set t to parts as string
    set AppleScript's text item delimiters to return
    set parts to text items of t
    set AppleScript's text item delimiters to "\\n"
    set t to parts as string
    set AppleScript's text item delimiters to linefeed
    set parts to text items of t
    set AppleScript's text item delimiters to "\\n"
    set t to parts as string
    set AppleScript's text item delimiters to tab
    set parts to text items of t
    set AppleScript's text item delimiters to "\\t"
    set t to parts as string
    set AppleScript's text item delimiters to ""
    return "\"" & t & "\""
end jsonString
"""


def _known_account_names() -> list[str]:
    """Return account names from mail_list_mailboxes for validation."""
    try:
        mbs = mail_list_mailboxes()
    except RuntimeError:
        return []
    return sorted({mb["account_name"] for mb in mbs if mb.get("account_name")})


def _validate_from_account(from_account: str | None) -> None:
    if from_account is None:
        return
    known = _known_account_names()
    if known and from_account not in known:
        raise RuntimeError(
            f"Unknown from_account: not in Mail accounts. Known: {', '.join(known)}"
        )


@mcp.tool(annotations=ToolAnnotations(title="Send Email"))
def mail_send(
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    reply_to_id: str | None = None,
    from_account: str | None = None,
    dry_run: bool = True,
) -> dict:
    """Send a Mail message. Default dry_run=True returns preview without sending."""
    cc = cc or []
    if not to:
        raise RuntimeError("mail_send requires at least one recipient in 'to'")

    if dry_run:
        return {
            "sent": False,
            "preview": {
                "to": list(to),
                "cc": list(cc),
                "subject": subject,
                "body": body,
                "from_account": from_account,
                "reply_to_id": reply_to_id,
            },
            "next_action": _tool_next_action(
                "mail_send",
                {
                    "to": list(to),
                    "subject": subject,
                    "body": body,
                    "cc": list(cc),
                    "reply_to_id": reply_to_id,
                    "from_account": from_account,
                    "dry_run": False,
                },
                label="Send this email",
            ),
        }

    _validate_from_account(from_account)

    args = [
        subject,
        body,
        from_account or "",
        "1",
        str(len(to)),
        str(len(cc)),
        *to,
        *cc,
    ]
    raw = run_applescript(_SEND_SCRIPT, *args)
    data = _parse_json(raw) or {}
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected mail_send payload shape")
    data.setdefault("sent", True)
    data.setdefault("next_action", _open_mail_app_next_action(label="Open Mail"))
    return data


@mcp.tool(annotations=ToolAnnotations(title="Create Draft"))
def mail_create_draft(
    to: list[str],
    subject: str,
    body: str,
    from_account: str | None = None,
) -> dict:
    """Create a Mail draft without sending."""
    if not to:
        raise RuntimeError("mail_create_draft requires at least one recipient in 'to'")
    _validate_from_account(from_account)

    args = [
        subject,
        body,
        from_account or "",
        "0",
        str(len(to)),
        "0",
        *to,
    ]
    raw = run_applescript(_SEND_SCRIPT, *args)
    data = _parse_json(raw) or {}
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected mail_create_draft payload shape")
    data.setdefault("draft_created", True)
    data.setdefault("draft_visible", True)
    data.setdefault("open_url", None)
    data.setdefault(
        "open_mail",
        {
            "app": "Mail",
            "action": "activate",
            "already_open": True,
        },
    )
    data.setdefault("next_action", _open_mail_app_next_action(label="Review draft in Mail"))
    data.setdefault("next_step", "Review and send the visible draft in Mail.")
    return data


# ---------------------------------------------------------------------------
# mail_open_message
# ---------------------------------------------------------------------------


def _canonical_message_id_for_open(identifier: str) -> tuple[str | None, dict[str, Any] | None]:
    needle = (identifier or "").strip()
    if not needle:
        return None, None
    try:
        row = get_mail_store_message(needle)
    except MailStoreUnavailable:
        row = None
    if row and row.get("id"):
        return str(row["id"]), row
    if "@" in needle:
        return needle, None
    return None, None


def _mail_message_url(message_id: str) -> str:
    text = (message_id or "").strip()
    if "@" in text and not (text.startswith("<") and text.endswith(">")):
        text = f"<{text.strip('<>')}>"
    return "message://" + quote(text, safe="")


@mcp.tool(annotations=ToolAnnotations(title="Open Mail Message"))
def mail_open_message(message_id: str, dry_run: bool = False) -> dict:
    """Open a Mail message in Mail.app by canonical or store-resolvable id."""
    canonical_id, row = _canonical_message_id_for_open(message_id)
    if not canonical_id:
        return {
            "error": "message_id_unresolved",
            "message": "Message could not be resolved to a canonical RFC Message-ID for Mail.app opening.",
            "recoverable": True,
            "message_id": message_id,
            "next_action": _tool_next_action(
                "mail_search",
                {"query": message_id, "limit": 10},
                label="Search for this email",
            ),
        }

    url = _mail_message_url(canonical_id)
    result: dict[str, Any] = {
        "opened": False,
        "message_id": canonical_id,
        "url": url,
        "open_url": url,
        "next_action": _open_url_next_action(url, label="Open in Mail"),
    }
    if row:
        result.update(
            {
                "subject": row.get("subject", ""),
                "sender": row.get("sender", ""),
                "date": row.get("date", ""),
                "account_name": row.get("account_name"),
                "mailbox_id": row.get("mailbox_id"),
                "mailbox_path": row.get("mailbox_path"),
            }
        )
    if dry_run:
        result["dry_run"] = True
        return result

    try:
        subprocess.run(["open", url], check=True, timeout=5)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
        return {
            **result,
            "error": "mail_open_failed",
            "message": str(exc),
            "recoverable": True,
        }

    result["opened"] = True
    result["next_action"] = _open_mail_app_next_action(label="Show Mail")
    return result


# ---------------------------------------------------------------------------
# mail_move_message
# ---------------------------------------------------------------------------

_MOVE_SCRIPT = r"""
on run argv
    set mid to item 1 of argv
    set targetMbId to item 2 of argv

    tell application "Mail"
        set src to missing value
        repeat with acct in accounts
            repeat with mb in mailboxes of acct
                try
                    if src is missing value then
                        set candidates to (messages of mb whose message id is mid)
                        if (count of candidates) > 0 then
                            set src to item 1 of candidates
                            exit repeat
                        end if
                    end if
                end try
                try
                    if src is missing value then
                        set candidates to (messages of mb whose id is (mid as integer))
                        if (count of candidates) > 0 then
                            set src to item 1 of candidates
                            exit repeat
                        end if
                    end if
                end try
            end repeat
            if src is not missing value then exit repeat
        end repeat

        if src is missing value then
            error "Message not found" number 404
        end if

        set dst to missing value
        repeat with acct in accounts
            repeat with mb in mailboxes of acct
                set mbIdStr to ""
                try
                    set mbIdStr to id of mb as text
                end try
                if mbIdStr is "" then
                    try
                        set mbIdStr to name of mb as string
                    end try
                end if
                if mbIdStr is targetMbId then
                    set dst to mb
                    exit repeat
                end if
            end repeat
            if dst is not missing value then exit repeat
        end repeat

        if dst is missing value then
            error "Target mailbox not found" number 404
        end if

        move src to dst
        return "{\"success\":true}"
    end tell
end run
"""


@mcp.tool(annotations=ToolAnnotations(title="Move Message"))
def mail_move_message(message_id: str, mailbox_id: str) -> dict:
    """Move a Mail message to a mailbox by persistent id."""
    try:
        resolved = resolve_target(
            mailbox_id,
            _mail_list_mailboxes_applescript(),
            scope="mailbox",
            preferences=PreferencesStore(),
            require_writable=True,
        )
    except ResolverError as exc:
        return exc.to_dict()

    resolved_mailbox_id = str(resolved.item["id"])
    raw = run_applescript(_MOVE_SCRIPT, message_id, resolved_mailbox_id)
    data = _parse_json(raw) or {"success": True}
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected mail_move_message payload shape")
    data["message_id"] = message_id
    data["mailbox_id"] = resolved_mailbox_id
    _add_message_actions(data)
    return data


# ---------------------------------------------------------------------------
# mail_flag_message
# ---------------------------------------------------------------------------

_FLAG_SCRIPT = r"""
on run argv
    set mid to item 1 of argv
    set flagFlag to (item 2 of argv) is "1"

    tell application "Mail"
        set target to missing value
        repeat with acct in accounts
            repeat with mb in mailboxes of acct
                try
                    if target is missing value then
                        set candidates to (messages of mb whose message id is mid)
                        if (count of candidates) > 0 then
                            set target to item 1 of candidates
                            exit repeat
                        end if
                    end if
                end try
                try
                    if target is missing value then
                        set candidates to (messages of mb whose id is (mid as integer))
                        if (count of candidates) > 0 then
                            set target to item 1 of candidates
                            exit repeat
                        end if
                    end if
                end try
            end repeat
            if target is not missing value then exit repeat
        end repeat

        if target is missing value then
            error "Message not found" number 404
        end if

        set flagged status of target to flagFlag
        return "{\"success\":true}"
    end tell
end run
"""


@mcp.tool(annotations=ToolAnnotations(title="Flag Message"))
def mail_flag_message(message_id: str, flagged: bool) -> dict:
    """Flag or unflag a Mail message by canonical id."""
    raw = run_applescript(_FLAG_SCRIPT, message_id, "1" if flagged else "0")
    data = _parse_json(raw) or {"success": True}
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected mail_flag_message payload shape")
    data["message_id"] = message_id
    data["flagged"] = flagged
    _add_message_actions(data)
    return data


# ---------------------------------------------------------------------------
# mail_delete
# ---------------------------------------------------------------------------

_DELETE_SCRIPT = r"""
on run argv
    set mid to item 1 of argv

    tell application "Mail"
        set target to missing value
        repeat with acct in accounts
            repeat with mb in mailboxes of acct
                try
                    if target is missing value then
                        set candidates to (messages of mb whose message id is mid)
                        if (count of candidates) > 0 then
                            set target to item 1 of candidates
                            exit repeat
                        end if
                    end if
                end try
                try
                    if target is missing value then
                        set candidates to (messages of mb whose id is (mid as integer))
                        if (count of candidates) > 0 then
                            set target to item 1 of candidates
                            exit repeat
                        end if
                    end if
                end try
            end repeat
            if target is not missing value then exit repeat
        end repeat

        if target is missing value then
            error "Message not found" number 404
        end if

        delete target
        return "{\"success\":true}"
    end tell
end run
"""


@mcp.tool(annotations=ToolAnnotations(title="Delete Message", destructiveHint=True))
def mail_delete(message_id: str, confirm: bool = False) -> dict:
    """Delete a Mail message by canonical id. Requires confirm=True."""
    if not confirm:
        return {
            "preview": f"Would delete message: {message_id}",
            "confirmed": False,
            "next_action": _tool_next_action(
                "mail_delete",
                {"message_id": message_id, "confirm": True},
                label="Confirm delete",
            ),
        }
    raw = run_applescript(_DELETE_SCRIPT, message_id)
    data = _parse_json(raw) or {"success": True}
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected mail_delete payload shape")
    data["message_id"] = message_id
    data.setdefault("next_action", _open_mail_app_next_action(label="Open Mail"))
    return data
