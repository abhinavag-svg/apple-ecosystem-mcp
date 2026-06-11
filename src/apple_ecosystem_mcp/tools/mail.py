from __future__ import annotations

import json
import os
import re
from typing import Any

from mcp.types import ToolAnnotations

from ..bridge import run_applescript, cache_inventory
from ..mail_store import (
    MailSearchQuery,
    MailStoreUnavailable,
    list_mail_store_mailboxes,
    search_mail_store,
)
from ..preferences import PreferencesStore
from ..resolver import ResolverError, resolve_target
from ..server import mcp

# Result-size policy per CLAUDE.md
_MAIL_SEARCH_DEFAULT = 20
_MAIL_SEARCH_MAX = 100
_MAIL_BODY_MAX_CHARS = 8_000
_MAIL_PREVIEW_CHARS = 200
_MAIL_PROVIDER_AUTO = "auto"
_MAIL_PROVIDER_LOCAL = "local"
_MAIL_PROVIDER_APPLESCRIPT = "applescript"
_MAIL_RECENT_DEFAULT_FIELDS = ["subject", "sender"]


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


def _mail_provider_mode(filters: dict) -> str:
    value = filters.get("provider")
    if value is None:
        value = filters.get("mail_provider")
    if value is None:
        value = os.environ.get("APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER", _MAIL_PROVIDER_AUTO)
    mode = str(value).strip().lower()
    if mode in {"store", "sqlite", "native", "local"}:
        return _MAIL_PROVIDER_LOCAL
    if mode in {"legacy", "script", "applescript"}:
        return _MAIL_PROVIDER_APPLESCRIPT
    return _MAIL_PROVIDER_AUTO


def _can_search_mail_store(
    query: str,
    search_fields: list[str],
    filters: dict,
    *,
    since: str | None,
    before: str | None,
    mailbox_id: str | None,
) -> bool:
    if "body" in search_fields:
        return False
    supported_filters = {
        "from_addr",
        "to_addr",
        "cc_addr",
        "unread",
        "flagged",
        "has_attachments",
        "account_name",
        "mailbox_ids",
        "provider",
        "mail_provider",
    }
    if any(key not in supported_filters for key in filters):
        return False
    effective_filters = [key for key in filters if key not in {"provider", "mail_provider"}]
    return bool(query or effective_filters or since or before or mailbox_id)


def _mail_query_impl(
    query: str,
    *,
    mailbox_id: str | None,
    limit: int,
    since: str | None,
    before: str | None,
    search_fields: list[str] | None,
    filters: dict | None,
    recent_mode: bool,
) -> list[dict]:
    query = (query or "").strip()
    capped = max(1, min(int(limit), _MAIL_SEARCH_MAX))

    filters = filters or {}
    search_fields = search_fields or ["subject"]
    search_fields = [field.lower() for field in search_fields]
    provider_mode = _mail_provider_mode(filters)

    store_capable = _can_search_mail_store(
        query,
        search_fields,
        filters,
        since=since,
        before=before,
        mailbox_id=mailbox_id,
    )
    if recent_mode and "body" not in search_fields:
        store_capable = True

    if provider_mode != _MAIL_PROVIDER_APPLESCRIPT and store_capable:
        try:
            data = _search_mail_store_scoped(
                query=query,
                mailbox_id=mailbox_id,
                limit=capped,
                since=since,
                before=before,
                search_fields=search_fields,
                filters=filters,
            )
            return data[:capped]
        except MailStoreUnavailable as exc:
            if provider_mode == _MAIL_PROVIDER_LOCAL:
                return [exc.to_dict()]

    # Build args list for AppleScript
    args = [
        query,
        mailbox_id or "",
        since or "",
        str(capped),
        filters.get("from_addr") or "",
        "1" if filters.get("unread") is True else ("0" if filters.get("unread") is False else ""),
        "1" if filters.get("flagged") is True else ("0" if filters.get("flagged") is False else ""),
        "1" if filters.get("has_attachments") is True else ("0" if filters.get("has_attachments") is False else ""),
        filters.get("account_name") or "",
        "1" if "body" in search_fields else "0",
        before or "",
    ]

    mailbox_ids = filters.get("mailbox_ids") or []
    args.append(str(len(mailbox_ids)))
    args.extend(mailbox_ids)

    args.append("1" if "subject" in search_fields else "0")
    args.append("1" if "sender" in search_fields else "0")
    args.append(filters.get("to_addr") or "")
    args.append(filters.get("cc_addr") or "")
    max_scan_total = capped * 40
    if "body" in search_fields:
        max_scan_total = capped * 15
    if filters.get("mailbox_ids") or mailbox_id:
        max_scan_total *= 2
    args.append(str(max(50, min(max_scan_total, 800))))
    args.append("1" if recent_mode else "0")

    raw = run_applescript(_SEARCH_SCRIPT, *args, timeout=35)
    data = _parse_json(raw) or []
    if not isinstance(data, list):
        raise RuntimeError("Unexpected mail_search payload shape")
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("preview"), str):
            item["preview"] = item["preview"][:_MAIL_PREVIEW_CHARS]
    return data[:capped]


def _search_with_mail_store(
    *,
    query: str,
    mailbox_id: str | None,
    limit: int,
    since: str | None,
    before: str | None,
    search_fields: list[str],
    filters: dict,
) -> list[dict[str, Any]]:
    mailbox_ids = filters.get("mailbox_ids") or []
    if not isinstance(mailbox_ids, list):
        mailbox_ids = []
    search = MailSearchQuery(
        query=query,
        limit=limit,
        since=since,
        before=before,
        mailbox_id=mailbox_id,
        mailbox_ids=tuple(str(item) for item in mailbox_ids),
        search_subject="subject" in search_fields,
        search_sender="sender" in search_fields,
        unread=filters.get("unread") if isinstance(filters.get("unread"), bool) else None,
        flagged=filters.get("flagged") if isinstance(filters.get("flagged"), bool) else None,
        has_attachments=(
            filters.get("has_attachments")
            if isinstance(filters.get("has_attachments"), bool)
            else None
        ),
        from_addr=filters.get("from_addr") or None,
        to_addr=filters.get("to_addr") or None,
        cc_addr=filters.get("cc_addr") or None,
    )
    return search_mail_store(search)


def _mailbox_inventory() -> list[dict[str, Any]]:
    try:
        rows = mail_list_mailboxes()
    except RuntimeError:
        return []
    return [row for row in rows if isinstance(row, dict)]


def _is_recency_style_search(query: str, filters: dict) -> bool:
    if query.strip():
        return False
    mailbox_ids = filters.get("mailbox_ids")
    return not mailbox_ids or isinstance(mailbox_ids, list)


def _group_mailboxes_by_account(
    inventory: list[dict[str, Any]],
    *,
    account_name: str | None = None,
    inbox_only: bool,
) -> list[tuple[str, list[dict[str, Any]]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in inventory:
        account = _nn(item.get("account_name"))
        path = _nn(item.get("path"))
        if not account or not path:
            continue
        if account_name and str(account) != account_name:
            continue
        grouped.setdefault(str(account), []).append(item)

    plans: list[tuple[str, list[dict[str, Any]]]] = []
    for account, items in grouped.items():
        candidates = items
        if inbox_only:
            inboxes = [item for item in items if item.get("default_candidate")]
            if inboxes:
                candidates = inboxes
        plans.append((account, candidates))
    return plans


def _mail_store_mailboxes_by_account(
    inventory: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    try:
        store_mailboxes = list_mail_store_mailboxes()
    except MailStoreUnavailable:
        return {}

    inventory_paths: dict[str, set[str]] = {}
    for account, items in _group_mailboxes_by_account(inventory, inbox_only=False):
        inventory_paths[account] = {str(item.get("path")) for item in items if item.get("path")}

    token_groups: dict[str, list[dict[str, Any]]] = {}
    for item in store_mailboxes:
        token = _nn(item.get("account_token"))
        path = _nn(item.get("mailbox_path"))
        if not token or not path:
            continue
        token_groups.setdefault(str(token), []).append(item)

    matched: dict[str, list[dict[str, Any]]] = {}
    for rows in token_groups.values():
        row_paths = {str(item.get("mailbox_path")) for item in rows if item.get("mailbox_path")}
        best_account: str | None = None
        best_score = 0
        tie = False
        for account, paths in inventory_paths.items():
            score = len(row_paths & paths)
            if score > best_score:
                best_account = account
                best_score = score
                tie = False
            elif score and score == best_score:
                tie = True
        if best_account and best_score > 0 and not tie:
            matched.setdefault(best_account, []).extend(rows)
    return matched


def _infer_store_account_label(rows: list[dict[str, Any]]) -> str | None:
    if not rows:
        return None
    token = str(rows[0].get("account_token") or "")
    paths = {str(item.get("mailbox_path") or "") for item in rows}
    lowered_paths = {path.casefold() for path in paths if path}
    if token.startswith("local://"):
        return None
    if token.startswith("ews://"):
        return "Hotmail"
    if token.startswith("imap://"):
        if "recovered messages (icloud)" in lowered_paths:
            return "iCloud"
        if {"inbox", "sent messages", "deleted messages"} & lowered_paths:
            return "iCloud"
        return "IMAP"
    return None


def _store_only_mailboxes_by_account() -> dict[str, list[dict[str, Any]]]:
    try:
        store_mailboxes = list_mail_store_mailboxes()
    except MailStoreUnavailable:
        return {}

    token_groups: dict[str, list[dict[str, Any]]] = {}
    for item in store_mailboxes:
        token = _nn(item.get("account_token"))
        if not token:
            continue
        token_groups.setdefault(str(token), []).append(item)

    matched: dict[str, list[dict[str, Any]]] = {}
    unnamed = 1
    for rows in token_groups.values():
        label = _infer_store_account_label(rows)
        if label is None:
            continue
        if label in matched:
            label = f"{label} {unnamed}"
            unnamed += 1
        matched[label] = rows
    return matched


def _sort_mail_results(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda item: str(item.get("date") or ""), reverse=True)


def _search_mail_store_scoped(
    *,
    query: str,
    mailbox_id: str | None,
    limit: int,
    since: str | None,
    before: str | None,
    search_fields: list[str],
    filters: dict,
) -> list[dict[str, Any]]:
    scoped_account = filters.get("account_name")
    if not scoped_account and not _is_recency_style_search(query, filters):
        return _search_with_mail_store(
            query=query,
            mailbox_id=mailbox_id,
            limit=limit,
            since=since,
            before=before,
            search_fields=search_fields,
            filters=filters,
        )

    inventory = _mailbox_inventory()
    explicit_mailbox_ids = filters.get("mailbox_ids")
    if mailbox_id or explicit_mailbox_ids:
        return _search_with_mail_store(
            query=query,
            mailbox_id=mailbox_id,
            limit=limit,
            since=since,
            before=before,
            search_fields=search_fields,
            filters=filters,
        )

    inbox_only = _is_recency_style_search(query, filters)
    inventory_groups: dict[str, list[dict[str, Any]]] = {}
    store_groups: dict[str, list[dict[str, Any]]] = {}
    if inventory:
        inventory_groups = dict(
            _group_mailboxes_by_account(
                inventory,
                account_name=scoped_account,
                inbox_only=False,
            )
        )
        store_groups = _mail_store_mailboxes_by_account(inventory)
    if not store_groups:
        store_groups = _store_only_mailboxes_by_account()
    account_names = [scoped_account] if scoped_account else list(store_groups.keys())
    if not account_names:
        return _search_with_mail_store(
            query=query,
            mailbox_id=mailbox_id,
            limit=limit,
            since=since,
            before=before,
            search_fields=search_fields,
            filters=filters,
        )

    collected: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    per_group_limit = limit
    if len(account_names) > 1:
        per_group_limit = max(limit, 10)

    base_filters = dict(filters)
    base_filters.pop("account_name", None)
    for account in account_names:
        store_mailboxes = store_groups.get(account) or []
        inventory_mailboxes = inventory_groups.get(account) or []
        if not store_mailboxes:
            continue
        if inbox_only:
            default_paths = {str(item.get("path")) for item in inventory_mailboxes if item.get("default_candidate") and item.get("path")}
            if not default_paths:
                default_paths = {
                    str(item.get("mailbox_path"))
                    for item in store_mailboxes
                    if str(item.get("mailbox_path") or "").casefold() == "inbox"
                }
            if default_paths:
                scoped_store_mailboxes = [
                    item for item in store_mailboxes if str(item.get("mailbox_path")) in default_paths
                ]
            else:
                scoped_store_mailboxes = store_mailboxes
        else:
            scoped_store_mailboxes = store_mailboxes
        if not scoped_store_mailboxes:
            continue
        scoped_filters = dict(base_filters)
        scoped_filters["mailbox_ids"] = [
            str(item.get("mailbox_url"))
            for item in scoped_store_mailboxes
            if item.get("mailbox_url")
        ]
        rows = _search_with_mail_store(
            query=query,
            mailbox_id=None,
            limit=per_group_limit,
            since=since,
            before=before,
            search_fields=search_fields,
            filters=scoped_filters,
        )
        for row in rows:
            if not isinstance(row, dict):
                continue
            row.setdefault("account_name", account)
            if not row.get("account_name"):
                row["account_name"] = account
            key = (str(row.get("id") or ""), str(row.get("internal_id") or ""))
            if key in seen:
                continue
            seen.add(key)
            collected.append(row)
    if not collected:
        return _search_with_mail_store(
            query=query,
            mailbox_id=mailbox_id,
            limit=limit,
            since=since,
            before=before,
            search_fields=search_fields,
            filters=filters,
        )
    return _sort_mail_results(collected)[:limit]


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
            set acct to account acctIdx
            set acctName to name of acct
            set mbCount to count of mailboxes of acct
            repeat with mbIdx from 1 to mbCount
                set mb to mailbox mbIdx of acct
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
                try
                    if class of containerMb is account then
                        exit repeat
                    end if
                end try
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


# ---------------------------------------------------------------------------
# mail_search
# ---------------------------------------------------------------------------

_SEARCH_SCRIPT = r"""
on run argv
    set qry to item 1 of argv
    set mbId to item 2 of argv
    set sinceStr to item 3 of argv
    set limitStr to item 4 of argv
    set fromAddr to item 5 of argv
    set unreadStr to item 6 of argv
    set flaggedStr to item 7 of argv
    set hasAttachStr to item 8 of argv
    set acctNameFilter to item 9 of argv
    set searchBodyStr to item 10 of argv
    set beforeStr to item 11 of argv
    set mbIdsCountStr to item 12 of argv

    set lim to (limitStr as integer)
    set searchBody to searchBodyStr is "1"
    set mbIdsCount to (mbIdsCountStr as integer)
    set mbIds to {}
    set mbIdsIdx to 13
    repeat mbIdsCount times
        set end of mbIds to item mbIdsIdx of argv
        set mbIdsIdx to mbIdsIdx + 1
    end repeat

    set searchSubjectStr to item mbIdsIdx of argv
    set searchSubject to searchSubjectStr is "1"
    set searchSenderStr to item (mbIdsIdx + 1) of argv
    set searchSender to searchSenderStr is "1"
    set toAddr to item (mbIdsIdx + 2) of argv
    set ccAddr to item (mbIdsIdx + 3) of argv
    set maxScanTotal to (item (mbIdsIdx + 4) of argv) as integer
    set recentMode to (item (mbIdsIdx + 5) of argv) is "1"

    -- Check if any filters are active
    set hasFilters to false
    if recentMode or unreadStr is not "" or flaggedStr is not "" or hasAttachStr is not "" or fromAddr is not "" or toAddr is not "" or ccAddr is not "" or acctNameFilter is not "" or mbIdsCount > 0 then
        set hasFilters to true
    end if

    if qry is "" and not hasFilters then
        return "[]"
    end if

    set output to "["
    set firstItem to true
    set count_ to 0
    set scannedTotal to 0

    tell application "Mail"
        repeat with acct in accounts
            if scannedTotal ≥ maxScanTotal then exit repeat
            set acctName to name of acct
            set checkAcctFilter to acctNameFilter is "" or acctName is acctNameFilter

            if checkAcctFilter then
                repeat with mb in mailboxes of acct
                    if scannedTotal ≥ maxScanTotal then exit repeat
                    set shouldSearch to false
                    if mbIdsCount > 0 then
                        set mbIdStr to ""
                        try
                            set mbIdStr to id of mb as text
                        end try
                        if mbIdStr is "" then
                            try
                                set mbIdStr to name of mb as string
                            end try
                        end if
                        repeat with mbIdToCheck in mbIds
                            if mbIdStr is mbIdToCheck then
                                set shouldSearch to true
                                exit repeat
                            end if
                        end repeat
                    else if mbId is "" then
                        set shouldSearch to true
                    else
                        set mbIdStr to ""
                        try
                            set mbIdStr to id of mb as text
                        end try
                        if mbIdStr is "" then
                            try
                                set mbIdStr to name of mb as string
                            end try
                        end if
                        if mbIdStr is mbId then
                            set shouldSearch to true
                        end if
                    end if

                    if shouldSearch then
                        set msgList to {}
                        set mCount to 0
                        try
                            set msgList to messages of mb
                            set mCount to count of msgList
                        end try

                        set scanLim to mCount
                        if hasFilters then
                            if scanLim > 250 then set scanLim to 250
                        else
                            if scanLim > 500 then set scanLim to 500
                        end if

                        repeat with offset_ from 0 to (scanLim - 1)
                            if count_ ≥ lim then exit repeat
                            if scannedTotal ≥ maxScanTotal then exit repeat
                            set idx_ to (mCount - offset_)
                            if idx_ < 1 then exit repeat
                            set scannedTotal to scannedTotal + 1

                            set msg to missing value
                            try
                                set msg to item idx_ of msgList
                            end try
                            if msg is missing value then
                                -- Skip invalid/unavailable message references.
                            else
                                set subj to ""
                                try
                                    set subj to subject of msg as string
                                end try
                                set snd to ""
                                if searchSender then
                                    try
                                        set snd to sender of msg as string
                                    end try
                                end if

                                set queryMatch to false
                                if qry is "" then
                                    set queryMatch to true
                                else if searchSubject and my containsCI(subj, qry) then
                                    set queryMatch to true
                                else if searchSender and my containsCI(snd, qry) then
                                    set queryMatch to true
                                else if searchBody then
                                    set bodyText to ""
                                    try
                                        set bodyText to content of msg
                                    end try
                                    if my containsCI(bodyText, qry) then
                                        set queryMatch to true
                                    end if
                                end if

                                if queryMatch then
                                        set msgDate to ""
                                        try
                                            set msgDate to (date received of msg) as «class isot» as string
                                        end try

                                        set dateInRange to true
                                        if sinceStr is not "" and (msgDate is "" or msgDate < sinceStr) then
                                            set dateInRange to false
                                        end if
                                        if beforeStr is not "" and (msgDate is "" or msgDate > beforeStr) then
                                            set dateInRange to false
                                        end if

                                        if dateInRange then
                                            set unreadMatch to true
                                            if unreadStr is not "" then
                                                set isUnread to not (read status of msg)
                                                if unreadStr is "1" then
                                                    set unreadMatch to isUnread
                                                else
                                                    set unreadMatch to not isUnread
                                                end if
                                            end if

                                            set flaggedMatch to true
                                            if flaggedStr is not "" then
                                                set isFlagged to flagged status of msg
                                                if flaggedStr is "1" then
                                                    set flaggedMatch to isFlagged
                                                else
                                                    set flaggedMatch to not isFlagged
                                                end if
                                            end if

                                            set attachMatch to true
                                            if hasAttachStr is not "" then
                                                set hasAttach to (count of mail attachments of msg) > 0
                                                if hasAttachStr is "1" then
                                                    set attachMatch to hasAttach
                                                else
                                                    set attachMatch to not hasAttach
                                                end if
                                            end if

                                            set fromMatch to true
                                            if fromAddr is not "" then
                                                set snd to ""
                                                try
                                                    set snd to sender of msg as string
                                                end try
                                                set fromMatch to my containsCI(snd, fromAddr)
                                            end if

                                            set toMatch to true
                                            if toAddr is not "" then
                                                set toAddresses to ""
                                                try
                                                    repeat with r in (to recipients of msg)
                                                        set toAddresses to toAddresses & (address of r as string) & " "
                                                    end repeat
                                                end try
                                                set toMatch to my containsCI(toAddresses, toAddr)
                                            end if

                                            set ccMatch to true
                                            if ccAddr is not "" then
                                                set ccAddresses to ""
                                                try
                                                    repeat with r in (cc recipients of msg)
                                                        set ccAddresses to ccAddresses & (address of r as string) & " "
                                                    end repeat
                                                end try
                                                set ccMatch to my containsCI(ccAddresses, ccAddr)
                                            end if

                                            if unreadMatch and flaggedMatch and attachMatch and fromMatch and toMatch and ccMatch then
                                                set snd to ""
                                                try
                                                    set snd to sender of msg as string
                                                end try
                                                set mid to ""
                                                try
                                                    set mid to message id of msg as string
                                                end try
                                                set internalId to ""
                                                try
                                                    set internalId to id of msg as string
                                                end try
                                                if mid is "" then set mid to internalId
                                                set preview to ""
                                                set thisMbId to ""
                                                try
                                                    set thisMbId to id of mb as string
                                                end try
                                                set hasAttach to (count of mail attachments of msg) > 0

                                                if not firstItem then set output to output & ","
                                                set firstItem to false
                                                set output to output & "{\"id\":" & my jsonString(mid) & ",\"internal_id\":" & my jsonString(internalId) & ",\"subject\":" & my jsonString(subj) & ",\"sender\":" & my jsonString(snd) & ",\"date\":" & my jsonString(msgDate) & ",\"preview\":" & my jsonString(preview) & ",\"mailbox_id\":" & my jsonString(thisMbId) & ",\"account_name\":" & my jsonString(acctName) & ",\"has_attachments\":" & (hasAttach as string) & "}"
                                                set count_ to count_ + 1
                                            end if
                                        end if
                                end if
                            end if
                        end repeat
                        if count_ ≥ lim then exit repeat
                    end if
                end repeat
            end if
            if count_ ≥ lim then exit repeat
            if scannedTotal ≥ maxScanTotal then exit repeat
        end repeat
    end tell
    return output & "]"
end run

on containsCI(hay, needle)
    try
        ignoring case
            return (hay contains needle)
        end ignoring
    on error
        return false
    end try
end containsCI

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


@mcp.tool(annotations=ToolAnnotations(title="Search Mail", readOnlyHint=True))
def mail_search(
    query: str,
    mailbox_id: str | None = None,
    limit: int = _MAIL_SEARCH_DEFAULT,
    since: str | None = None,
    before: str | None = None,
    search_fields: list[str] | None = None,
    filters: dict | None = None,
) -> list[dict]:
    """Search Mail by literal query text or explicit fielded filters.

    Use this tool for keyword-style lookups such as sender, subject, or body
    search. For chronological retrieval, prefer ``mail_recent`` instead of
    inventing keywords. If you need a time window here, pass the user's literal
    query string and constrain it with ``since`` and/or ``before``.

    Args:
        query: Literal search query string. Use an empty string only with explicit filters.
        mailbox_id: Optional single mailbox ID (backward compatibility)
        limit: Result limit (1-100, default 20)
        since: ISO date string for start of date range
        before: ISO date string for end of date range
        search_fields: List of fields to search (default ["subject"]; can include "sender" and "body")
        filters: Optional dict with keys: from_addr, to_addr, cc_addr, unread (bool),
                 flagged (bool), has_attachments (bool), account_name, mailbox_ids (list)
    """
    return _mail_query_impl(
        query,
        mailbox_id=mailbox_id,
        limit=limit,
        since=since,
        before=before,
        search_fields=search_fields,
        filters=filters,
        recent_mode=False,
    )


@mcp.tool(annotations=ToolAnnotations(title="Recent Mail", readOnlyHint=True))
def mail_recent(
    limit: int = _MAIL_SEARCH_DEFAULT,
    since: str | None = None,
    before: str | None = None,
    mailbox_id: str | None = None,
    filters: dict | None = None,
) -> list[dict]:
    """Return the most recent Mail messages in chronological order.

    Use this tool for recency-style requests such as "latest", "recent",
    "overnight", or "today". Do not synthesize topic keywords; instead pass
    explicit ``since`` / ``before`` bounds and optional structured filters such
    as ``account_name``, ``mailbox_ids``, or ``unread``.

    Args:
        limit: Result limit (1-100, default 20)
        since: Optional ISO date string for the start of the window
        before: Optional ISO date string for the end of the window
        mailbox_id: Optional single mailbox ID (backward compatibility)
        filters: Optional dict with keys: unread (bool), flagged (bool),
                 has_attachments (bool), account_name, mailbox_ids (list),
                 from_addr, to_addr, cc_addr, provider
    """
    return _mail_query_impl(
        "",
        mailbox_id=mailbox_id,
        limit=limit,
        since=since,
        before=before,
        search_fields=list(_MAIL_RECENT_DEFAULT_FIELDS),
        filters=filters,
        recent_mode=True,
    )


# ---------------------------------------------------------------------------
# mail_get_thread
# ---------------------------------------------------------------------------

_GET_THREAD_SCRIPT = r"""
on run argv
    set mid to item 1 of argv
    set includeBody to (item 2 of argv) is "1"

    tell application "Mail"
        set target to missing value
        set mbId to ""
        set acctName to ""
        repeat with acct in accounts
            repeat with mb in mailboxes of acct
                set candidates to {}
                try
                    set candidates to (messages of mb whose message id is mid)
                end try
                if (count of candidates) = 0 then
                    try
                        set candidates to (messages of mb whose id is (mid as integer))
                    end try
                end if
                if (count of candidates) > 0 then
                    set target to item 1 of candidates
                    set mbId to my mailboxIdentifier(mb)
                    set acctName to name of acct
                    exit repeat
                end if
            end repeat
            if target is not missing value then exit repeat
        end repeat

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
    raw = run_applescript(_GET_THREAD_SCRIPT, message_id, "1" if include_body else "0")
    data = _parse_json(raw)
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected mail_get_thread payload shape")

    if include_body:
        body = data.get("body", "") or ""
        body = _strip_html_and_base64(body)
        data["body"] = _truncate_body(body)
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
            set msg to make new outgoing message with properties {subject:subj, content:bodyText, visible:false, sender:fromAccount}
        else
            set msg to make new outgoing message with properties {subject:subj, content:bodyText, visible:false}
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
            return "{\"success\":true,\"draft_created\":true}"
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
    return data


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
            mail_list_mailboxes(),
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
        return {"preview": f"Would delete message: {message_id}", "confirmed": False}
    raw = run_applescript(_DELETE_SCRIPT, message_id)
    data = _parse_json(raw) or {"success": True}
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected mail_delete payload shape")
    data["message_id"] = message_id
    return data
