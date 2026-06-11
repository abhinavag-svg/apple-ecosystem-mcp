from __future__ import annotations

import json
import os
from typing import Any, Callable

from .bridge import run_applescript
from .mail_store import (
    MailSearchQuery,
    MailStoreUnavailable,
    list_mail_store_mailboxes,
    search_mail_store,
)

MAIL_SEARCH_DEFAULT = 20
MAIL_SEARCH_MAX = 100
MAIL_PREVIEW_CHARS = 200
MAIL_PROVIDER_AUTO = "auto"
MAIL_PROVIDER_LOCAL = "local"
MAIL_PROVIDER_APPLESCRIPT = "applescript"
MAIL_RECENT_DEFAULT_FIELDS = ("subject", "sender")


def _parse_json(raw: str) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Malformed AppleScript JSON output: {exc.msg}") from exc


def _nn(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str) and (value == "" or value == "missing value"):
        return None
    return value


def _mail_provider_mode(filters: dict) -> str:
    value = filters.get("provider")
    if value is None:
        value = filters.get("mail_provider")
    if value is None:
        value = os.environ.get("APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER", MAIL_PROVIDER_AUTO)
    mode = str(value).strip().lower()
    if mode in {"store", "sqlite", "native", "local"}:
        return MAIL_PROVIDER_LOCAL
    if mode in {"legacy", "script", "applescript"}:
        return MAIL_PROVIDER_APPLESCRIPT
    return MAIL_PROVIDER_AUTO


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


def _mailbox_inventory(
    mailbox_inventory_fn: Callable[[], list[dict]] | None,
) -> list[dict[str, Any]]:
    if mailbox_inventory_fn is None:
        return []
    try:
        rows = mailbox_inventory_fn()
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
    mailbox_inventory_fn: Callable[[], list[dict]] | None,
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

    inventory = _mailbox_inventory(mailbox_inventory_fn)
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
            default_paths = {
                str(item.get("path"))
                for item in inventory_mailboxes
                if item.get("default_candidate") and item.get("path")
            }
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


def _build_search_args(
    *,
    query: str,
    mailbox_id: str | None,
    capped: int,
    since: str | None,
    before: str | None,
    search_fields: list[str],
    filters: dict,
    recent_mode: bool,
) -> list[str]:
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
    return args


def _execute_search(
    *,
    query: str,
    mailbox_id: str | None,
    limit: int,
    since: str | None,
    before: str | None,
    search_fields: list[str] | None,
    filters: dict | None,
    recent_mode: bool,
    mailbox_inventory_fn: Callable[[], list[dict]] | None,
) -> list[dict]:
    query = (query or "").strip()
    capped = max(1, min(int(limit), MAIL_SEARCH_MAX))

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

    if provider_mode != MAIL_PROVIDER_APPLESCRIPT and store_capable:
        try:
            data = _search_mail_store_scoped(
                query=query,
                mailbox_id=mailbox_id,
                limit=capped,
                since=since,
                before=before,
                search_fields=search_fields,
                filters=filters,
                mailbox_inventory_fn=mailbox_inventory_fn,
            )
            return data[:capped]
        except MailStoreUnavailable as exc:
            if provider_mode == MAIL_PROVIDER_LOCAL:
                return [exc.to_dict()]

    args = _build_search_args(
        query=query,
        mailbox_id=mailbox_id,
        capped=capped,
        since=since,
        before=before,
        search_fields=search_fields,
        filters=filters,
        recent_mode=recent_mode,
    )
    raw = run_applescript(_SEARCH_SCRIPT, *args, timeout=35)
    data = _parse_json(raw) or []
    if not isinstance(data, list):
        raise RuntimeError("Unexpected mail_search payload shape")
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("preview"), str):
            item["preview"] = item["preview"][:MAIL_PREVIEW_CHARS]
    return data[:capped]


def search_mail(
    query: str,
    *,
    mailbox_id: str | None = None,
    limit: int = MAIL_SEARCH_DEFAULT,
    since: str | None = None,
    before: str | None = None,
    search_fields: list[str] | None = None,
    filters: dict | None = None,
    mailbox_inventory_fn: Callable[[], list[dict]] | None = None,
) -> list[dict]:
    return _execute_search(
        query=query,
        mailbox_id=mailbox_id,
        limit=limit,
        since=since,
        before=before,
        search_fields=search_fields,
        filters=filters,
        recent_mode=False,
        mailbox_inventory_fn=mailbox_inventory_fn,
    )


def recent_mail(
    *,
    limit: int = MAIL_SEARCH_DEFAULT,
    since: str | None = None,
    before: str | None = None,
    mailbox_id: str | None = None,
    filters: dict | None = None,
    mailbox_inventory_fn: Callable[[], list[dict]] | None = None,
) -> list[dict]:
    return _execute_search(
        query="",
        mailbox_id=mailbox_id,
        limit=limit,
        since=since,
        before=before,
        search_fields=list(MAIL_RECENT_DEFAULT_FIELDS),
        filters=filters,
        recent_mode=True,
        mailbox_inventory_fn=mailbox_inventory_fn,
    )


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
