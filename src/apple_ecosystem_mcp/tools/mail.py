from __future__ import annotations

import json
import re
from typing import Any

from mcp.types import ToolAnnotations

from ..bridge import run_applescript
from ..server import mcp

# Result-size policy per CLAUDE.md
_MAIL_SEARCH_DEFAULT = 20
_MAIL_SEARCH_MAX = 100
_MAIL_BODY_MAX_CHARS = 8_000
_MAIL_PREVIEW_CHARS = 200


def _parse_json(raw: str) -> Any:
    """Parse AppleScript JSON output; raise RuntimeError on malformed payload."""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Malformed AppleScript JSON output: {e.msg}") from e


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
                set output to output & "{\"name\":" & my jsonString(mbName) & ",\"id\":" & my jsonString(mbId) & ",\"account_name\":" & my jsonString(acctName) & ",\"path\":" & my jsonString(mbPath) & "}"
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
def mail_list_mailboxes() -> list[dict]:
    """List all mailboxes across every Mail account with canonical ids."""
    raw = run_applescript(_LIST_MAILBOXES_SCRIPT)
    data = _parse_json(raw) or []
    if not isinstance(data, list):
        raise RuntimeError("Unexpected mail_list_mailboxes payload shape")
    return data


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

    -- Check if any filters are active
    set hasFilters to false
    if unreadStr is not "" or flaggedStr is not "" or hasAttachStr is not "" or fromAddr is not "" or toAddr is not "" or ccAddr is not "" or acctNameFilter is not "" or mbIdsCount > 0 then
        set hasFilters to true
    end if

    if qry is "" and not hasFilters then
        return "[]"
    end if

    set output to "["
    set firstItem to true
    set count_ to 0

    tell application "Mail"
        repeat with acct in accounts
            set acctName to name of acct
            set checkAcctFilter to acctNameFilter is "" or acctName is acctNameFilter

            if checkAcctFilter then
                repeat with mb in mailboxes of acct
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
                            if scanLim > 1000 then set scanLim to 1000
                        else
                            if scanLim > 5000 then set scanLim to 5000
                        end if

                        repeat with offset_ from 0 to (scanLim - 1)
                            if count_ ≥ lim then exit repeat
                            set idx_ to (mCount - offset_)
                            if idx_ < 1 then exit repeat

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
                                                set bodyText to ""
                                                try
                                                    set bodyText to content of msg
                                                end try
                                                if (length of bodyText) > 200 then
                                                    set preview to text 1 thru 200 of bodyText
                                                else
                                                    set preview to bodyText
                                                end if
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
    """Search Mail messages with optional filters; returns canonical ids, capped at 100 results.

    Args:
        query: Search query string
        mailbox_id: Optional single mailbox ID (backward compatibility)
        limit: Result limit (1-100, default 20)
        since: ISO date string for start of date range
        before: ISO date string for end of date range
        search_fields: List of fields to search (default ["subject"]; can include "sender" and "body")
        filters: Optional dict with keys: from_addr, to_addr, cc_addr, unread (bool),
                 flagged (bool), has_attachments (bool), account_name, mailbox_ids (list)
    """
    query = (query or "").strip()
    capped = max(1, min(int(limit), _MAIL_SEARCH_MAX))

    filters = filters or {}
    search_fields = search_fields or ["subject"]

    # Build args list for AppleScript
    search_fields = [field.lower() for field in search_fields]
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

    raw = run_applescript(_SEARCH_SCRIPT, *args)
    data = _parse_json(raw) or []
    if not isinstance(data, list):
        raise RuntimeError("Unexpected mail_search payload shape")
    for item in data:
        if isinstance(item, dict) and isinstance(item.get("preview"), str):
            item["preview"] = item["preview"][:_MAIL_PREVIEW_CHARS]
    return data[:capped]


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
                    set mbId to id of mb as string
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


@mcp.tool(annotations=ToolAnnotations(title="Move Message", destructiveHint=True))
def mail_move_message(message_id: str, mailbox_id: str) -> dict:
    """Move a Mail message to a mailbox by persistent id."""
    raw = run_applescript(_MOVE_SCRIPT, message_id, mailbox_id)
    data = _parse_json(raw) or {"success": True}
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected mail_move_message payload shape")
    data["message_id"] = message_id
    data["mailbox_id"] = mailbox_id
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
def mail_delete(message_id: str) -> dict:
    """Delete a Mail message by canonical id."""
    raw = run_applescript(_DELETE_SCRIPT, message_id)
    data = _parse_json(raw) or {"success": True}
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected mail_delete payload shape")
    data["message_id"] = message_id
    return data
