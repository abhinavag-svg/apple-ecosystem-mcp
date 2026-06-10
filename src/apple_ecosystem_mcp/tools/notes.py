from __future__ import annotations

import gzip
import json
import os
import re
import sqlite3
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import quote

from mcp.types import ToolAnnotations

from ..bridge import run_applescript
from ..server import mcp

_LIST_LIMIT_DEFAULT = 50
_LIST_LIMIT_MAX = 200
_NOTE_TEXT_MAX_CHARS = 20_000
_APPLE_REFERENCE_OFFSET = 978_307_200


def _parse_json(raw: str) -> Any:
    try:
        return json.loads(raw) if raw else []
    except json.JSONDecodeError as exc:
        raise RuntimeError("Failed to parse Notes response") from exc


def _nn(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str) and (value == "" or value == "missing value"):
        return None
    return value


def _limit(value: int, maximum: int = _LIST_LIMIT_MAX) -> int:
    return max(1, min(int(value), maximum))


def _plain_text(value: str | None, max_chars: int = _NOTE_TEXT_MAX_CHARS) -> str | None:
    if value is None:
        return None
    text = re.sub(r"<br\s*/?>", "\n", value, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > max_chars:
        return text[:max_chars] + "..."
    return text


def _normalize_note(row: dict) -> dict:
    body = _nn(row.get("body"))
    text = _nn(row.get("text"))
    if text is None:
        text = _plain_text(body)
    elif isinstance(text, str) and len(text) > _NOTE_TEXT_MAX_CHARS:
        text = text[:_NOTE_TEXT_MAX_CHARS] + "..."
    body_format = _nn(row.get("body_format")) or "plain_text"
    return {
        "id": _nn(row.get("id")),
        "title": _nn(row.get("title")),
        "body": text if body_format == "plain_text" else body,
        "text": text,
        "body_format": body_format,
        "account": _nn(row.get("account")),
        "folder": _nn(row.get("folder")),
        "created": _nn(row.get("created")),
        "modified": _nn(row.get("modified")),
    }


def _normalize_note_summary(row: dict) -> dict:
    note = _normalize_note(row)
    text = note.get("text") or ""
    note["preview"] = text[:240]
    note.pop("body", None)
    note.pop("text", None)
    return note


def _notes_store_path() -> Path:
    override = os.environ.get("APPLE_ECOSYSTEM_MCP_NOTES_STORE")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Group Containers" / "group.com.apple.notes" / "NoteStore.sqlite"


def _read_note_from_store(
    *,
    title: str | None,
    note_id: str | None,
    account: str | None,
) -> dict | None:
    if account:
        return None
    path = _notes_store_path()
    if not path.exists():
        return None

    try:
        db_uri = f"file:{quote(str(path), safe='/')}?mode=ro"
        conn = sqlite3.connect(db_uri, uri=True)
    except sqlite3.Error:
        return None

    try:
        conn.row_factory = sqlite3.Row
        where = ["n.ZMARKEDFORDELETION = 0"]
        params: list[Any] = []
        pk = _note_pk_from_id(note_id)
        if pk is not None:
            where.append("n.Z_PK = ?")
            params.append(pk)
        elif note_id:
            where.append("n.ZIDENTIFIER = ?")
            params.append(note_id)
        elif title:
            where.append("lower(n.ZTITLE1) = lower(?)")
            params.append(title)
        else:
            return None

        sql = f"""
            select
                n.Z_PK as id,
                n.ZIDENTIFIER as identifier,
                n.ZTITLE1 as title,
                n.ZMODIFICATIONDATE1 as modified,
                n.ZCREATIONDATE1 as created,
                d.ZDATA as data
            from ZICCLOUDSYNCINGOBJECT n
            left join ZICNOTEDATA d on d.Z_PK = n.ZNOTEDATA
            where {" and ".join(where)}
            order by n.ZMODIFICATIONDATE1 desc
            limit 1
        """
        row = conn.execute(sql, params).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()

    if row is None:
        return None

    text = _extract_note_text_from_blob(row["data"])
    if text is None:
        return None
    text = _truncate_text(text, _NOTE_TEXT_MAX_CHARS)
    identifier = row["identifier"] or f"x-coredata://local/ICNote/p{row['id']}"
    return {
        "id": identifier,
        "title": _nn(row["title"]),
        "body": text,
        "text": text,
        "body_format": "plain_text",
        "account": None,
        "folder": None,
        "created": _format_apple_reference_date(row["created"]),
        "modified": _format_apple_reference_date(row["modified"]),
    }


def _note_pk_from_id(note_id: str | None) -> int | None:
    if not note_id:
        return None
    match = re.search(r"/p(\d+)\b", note_id)
    if match:
        return int(match.group(1))
    if note_id.isdigit():
        return int(note_id)
    return None


def _extract_note_text_from_blob(blob: bytes | None) -> str | None:
    if not blob:
        return None
    try:
        data = gzip.decompress(blob)
    except (OSError, EOFError):
        data = blob
    candidates = _protobuf_text_candidates(data)
    if not candidates:
        return None
    return max(candidates, key=len).strip() or None


def _protobuf_text_candidates(data: bytes, *, depth: int = 0) -> list[str]:
    candidates: list[str] = []
    i = 0
    while i < len(data):
        key, i = _read_varint(data, i)
        if key is None:
            break
        wire_type = key & 7
        if wire_type == 0:
            _, i = _read_varint(data, i)
            if i < 0:
                break
        elif wire_type == 1:
            i += 8
        elif wire_type == 5:
            i += 4
        elif wire_type == 2:
            length, i = _read_varint(data, i)
            if length is None or i + length > len(data):
                break
            value = data[i : i + length]
            i += length
            text = _decode_printable_text(value)
            if text is not None:
                candidates.append(text)
            if depth < 4 and len(value) > 2:
                candidates.extend(_protobuf_text_candidates(value, depth=depth + 1))
        else:
            break
    return candidates


def _read_varint(data: bytes, start: int) -> tuple[int | None, int]:
    result = 0
    shift = 0
    i = start
    while i < len(data) and shift <= 63:
        byte = data[i]
        i += 1
        result |= (byte & 0x7F) << shift
        if byte < 0x80:
            return result, i
        shift += 7
    return None, -1


def _decode_printable_text(value: bytes) -> str | None:
    try:
        text = value.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if not text.strip():
        return None
    printable = sum(ch.isprintable() or ch in "\n\r\t" for ch in text)
    if printable / max(1, len(text)) < 0.95:
        return None
    return text


def _truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _format_apple_reference_date(value: Any) -> str | None:
    if value is None:
        return None
    try:
        timestamp = float(value) + _APPLE_REFERENCE_OFFSET
    except (TypeError, ValueError):
        return None
    from datetime import datetime

    return datetime.fromtimestamp(timestamp).isoformat(timespec="seconds")


_JSON_HELPERS = r"""
on _js(v)
    if v is missing value then return "null"
    set s to v as string
    set out to ""
    repeat with i from 1 to length of s
        set ch to character i of s
        set c to id of ch
        if c is 34 then
            set out to out & "\\\""
        else if c is 92 then
            set out to out & "\\\\"
        else if c is 10 then
            set out to out & "\\n"
        else if c is 13 then
            set out to out & "\\r"
        else if c is 9 then
            set out to out & "\\t"
        else if c < 32 then
            set out to out & " "
        else
            set out to out & ch
        end if
    end repeat
    return "\"" & out & "\""
end _js

on _iso(d)
    if d is missing value then return "null"
    return "\"" & ((d as «class isot») as string) & "\""
end _iso

on _containsCI(hay, needle)
    if needle is "" then return true
    try
        ignoring case
            return ((hay as string) contains (needle as string))
        end ignoring
    on error
        return false
    end try
end _containsCI

on _sameCI(left_, right_)
    if right_ is "" then return true
    try
        ignoring case
            return ((left_ as string) is (right_ as string))
        end ignoring
    on error
        return false
    end try
end _sameCI

on _note_row(n, folderName, accountName, includeBody)
    set nid to ""
    set ntitle to ""
    set nbody to ""
    set cdate to missing value
    set mdate to missing value
    tell application "Notes"
        try
            set nid to id of n
        end try
        try
            set ntitle to name of n
        end try
        if includeBody then
            try
                set nbody to body of n
            end try
        end if
        try
            set cdate to creation date of n
        end try
        try
            set mdate to modification date of n
        end try
    end tell
    return "{\"id\":" & my _js(nid) & ",\"title\":" & my _js(ntitle) & ",\"body\":" & my _js(nbody) & ",\"body_format\":\"html\",\"account\":" & my _js(accountName) & ",\"folder\":" & my _js(folderName) & ",\"created\":" & my _iso(cdate) & ",\"modified\":" & my _iso(mdate) & "}"
end _note_row

on _note_row_plain_text(n, folderName, accountName)
    set nid to ""
    set ntitle to ""
    set ntext to ""
    set cdate to missing value
    set mdate to missing value
    tell application "Notes"
        try
            set nid to id of n
        end try
        try
            set ntitle to name of n
        end try
        try
            set ntext to («class text» of n) as string
        end try
        try
            set cdate to creation date of n
        end try
        try
            set mdate to modification date of n
        end try
    end tell
    return "{\"id\":" & my _js(nid) & ",\"title\":" & my _js(ntitle) & ",\"body\":" & my _js(ntext) & ",\"text\":" & my _js(ntext) & ",\"body_format\":\"plain_text\",\"account\":" & my _js(accountName) & ",\"folder\":" & my _js(folderName) & ",\"created\":" & my _iso(cdate) & ",\"modified\":" & my _iso(mdate) & "}"
end _note_row_plain_text
"""


_ACCOUNTS_SCRIPT = _JSON_HELPERS + r"""
on run argv
    set rows to {}
    tell application "Notes"
        repeat with a in accounts
            set aid to ""
            try
                set aid to id of a
            end try
            set end of rows to "{\"id\":" & my _js(aid) & ",\"name\":" & my _js(name of a) & ",\"kind\":\"notes_account\"}"
        end repeat
    end tell
    set AppleScript's text item delimiters to ","
    set out to "[" & (rows as string) & "]"
    set AppleScript's text item delimiters to ""
    return out
end run
"""


_FOLDERS_SCRIPT = _JSON_HELPERS + r"""
on run argv
    set accountFilter to item 1 of argv
    set rows to {}
    tell application "Notes"
        repeat with a in accounts
            set accountName to name of a
            if my _sameCI(accountName, accountFilter) then
                repeat with f in folders of a
                    set fid to ""
                    try
                        set fid to id of f
                    end try
                    set end of rows to "{\"id\":" & my _js(fid) & ",\"name\":" & my _js(name of f) & ",\"kind\":\"notes_folder\",\"account\":" & my _js(accountName) & ",\"path\":" & my _js(accountName & "/" & (name of f as string)) & "}"
                end repeat
            end if
        end repeat
    end tell
    set AppleScript's text item delimiters to ","
    set out to "[" & (rows as string) & "]"
    set AppleScript's text item delimiters to ""
    return out
end run
"""


_LIST_SCRIPT = _JSON_HELPERS + r"""
on run argv
    set accountFilter to item 1 of argv
    set folderFilter to item 2 of argv
    set queryText to item 3 of argv
    set lim to (item 4 of argv) as integer
    set includeBody to (item 5 of argv is "true")
    set rows to {}
    set count_ to 0
    tell application "Notes"
        repeat with a in accounts
            if count_ ≥ lim then exit repeat
            set accountName to name of a
            if my _sameCI(accountName, accountFilter) then
                repeat with f in folders of a
                    if count_ ≥ lim then exit repeat
                    set folderName to name of f
                    if my _sameCI(folderName, folderFilter) then
                        repeat with n in notes of f
                            if count_ ≥ lim then exit repeat
                            set ntitle to ""
                            try
                                set ntitle to name of n
                            end try
                            set matchesQuery to false
                            if queryText is "" then
                                set matchesQuery to true
                            else if my _containsCI(ntitle, queryText) then
                                set matchesQuery to true
                            else
                                set nbody to ""
                                try
                                    set nbody to body of n
                                end try
                                if my _containsCI(nbody, queryText) then set matchesQuery to true
                            end if
                            if matchesQuery then
                                set end of rows to my _note_row(n, folderName, accountName, includeBody)
                                set count_ to count_ + 1
                            end if
                        end repeat
                    end if
                end repeat
            end if
        end repeat
    end tell
    set AppleScript's text item delimiters to ","
    set out to "[" & (rows as string) & "]"
    set AppleScript's text item delimiters to ""
    return out
end run
"""


_READ_SCRIPT = _JSON_HELPERS + r"""
on run argv
    set targetID to item 1 of argv
    set targetTitle to item 2 of argv
    set accountFilter to item 3 of argv
    tell application "Notes"
        repeat with a in accounts
            set accountName to name of a
            if my _sameCI(accountName, accountFilter) then
                repeat with f in folders of a
                    set folderName to name of f
                    repeat with n in notes of f
                        set nid to ""
                        try
                            set nid to id of n
                        end try
                        set ntitle to ""
                        try
                            set ntitle to name of n
                        end try
                        if (targetID is not "" and nid is targetID) or (targetID is "" and my _sameCI(ntitle, targetTitle)) then
                            return my _note_row_plain_text(n, folderName, accountName)
                        end if
                    end repeat
                end repeat
            end if
        end repeat
    end tell
    return "null"
end run
"""


_CREATE_SCRIPT = _JSON_HELPERS + r"""
on run argv
    set targetFolder to item 1 of argv
    set titleText to item 2 of argv
    set bodyText to item 3 of argv
    set accountFilter to item 4 of argv
    tell application "Notes"
        repeat with a in accounts
            set accountName to name of a
            if my _sameCI(accountName, accountFilter) then
                repeat with f in folders of a
                    if my _sameCI(name of f, targetFolder) then
                        set newNote to make new note at f with properties {name:titleText, body:bodyText}
                        return my _note_row(newNote, name of f, accountName, true)
                    end if
                end repeat
            end if
        end repeat
    end tell
    error "Notes folder not found"
end run
"""


_APPEND_SCRIPT = _JSON_HELPERS + r"""
on run argv
    set targetID to item 1 of argv
    set targetTitle to item 2 of argv
    set appendText to item 3 of argv
    set accountFilter to item 4 of argv
    tell application "Notes"
        repeat with a in accounts
            set accountName to name of a
            if my _sameCI(accountName, accountFilter) then
                repeat with f in folders of a
                    set folderName to name of f
                    repeat with n in notes of f
                        set nid to ""
                        try
                            set nid to id of n
                        end try
                        set ntitle to ""
                        try
                            set ntitle to name of n
                        end try
                        if (targetID is not "" and nid is targetID) or (targetID is "" and my _sameCI(ntitle, targetTitle)) then
                            set oldBody to ""
                            try
                                set oldBody to body of n
                            end try
                            set body of n to oldBody & "<br>" & appendText
                            return my _note_row(n, folderName, accountName, true)
                        end if
                    end repeat
                end repeat
            end if
        end repeat
    end tell
    error "Note not found"
end run
"""


_DELETE_SCRIPT = _JSON_HELPERS + r"""
on run argv
    set targetID to item 1 of argv
    set targetTitle to item 2 of argv
    set accountFilter to item 3 of argv
    tell application "Notes"
        repeat with a in accounts
            set accountName to name of a
            if my _sameCI(accountName, accountFilter) then
                repeat with f in folders of a
                    repeat with n in notes of f
                        set nid to ""
                        try
                            set nid to id of n
                        end try
                        set ntitle to ""
                        try
                            set ntitle to name of n
                        end try
                        if (targetID is not "" and nid is targetID) or (targetID is "" and my _sameCI(ntitle, targetTitle)) then
                            delete n
                            return "{\"id\":" & my _js(nid) & ",\"success\":true}"
                        end if
                    end repeat
                end repeat
            end if
        end repeat
    end tell
    error "Note not found"
end run
"""


@mcp.tool(annotations=ToolAnnotations(title="List Notes Accounts", readOnlyHint=True))
def notes_accounts() -> list[dict]:
    """List Notes accounts."""
    rows = _parse_json(run_applescript(_ACCOUNTS_SCRIPT, timeout=20))
    return [row for row in rows if isinstance(row, dict)]


@mcp.tool(annotations=ToolAnnotations(title="List Notes Folders", readOnlyHint=True))
def notes_folders(account: str | None = None) -> list[dict]:
    """List Notes folders, optionally scoped to one account."""
    rows = _parse_json(run_applescript(_FOLDERS_SCRIPT, account or "", timeout=20))
    return [row for row in rows if isinstance(row, dict)]


@mcp.tool(annotations=ToolAnnotations(title="List Notes", readOnlyHint=True))
def notes_list(
    folder: str | None = None,
    account: str | None = None,
    limit: int = _LIST_LIMIT_DEFAULT,
) -> list[dict]:
    """List note summaries/previews only. Use notes_read to fetch full note content."""
    rows = _parse_json(
        run_applescript(_LIST_SCRIPT, account or "", folder or "", "", str(_limit(limit)), "false", timeout=30)
    )
    return [_normalize_note_summary(row) for row in rows if isinstance(row, dict)]


@mcp.tool(annotations=ToolAnnotations(title="Search Notes", readOnlyHint=True))
def notes_search(
    query: str,
    account: str | None = None,
    folder: str | None = None,
    limit: int = _LIST_LIMIT_DEFAULT,
) -> list[dict]:
    """Search note titles and bodies, returning summaries/previews only. Use notes_read with the returned id to fetch full content."""
    rows = _parse_json(
        run_applescript(_LIST_SCRIPT, account or "", folder or "", query, str(_limit(limit)), "false", timeout=30)
    )
    return [_normalize_note_summary(row) for row in rows if isinstance(row, dict)]


@mcp.tool(annotations=ToolAnnotations(title="Read Note", readOnlyHint=True))
def notes_read(
    title: str | None = None,
    note_id: str | None = None,
    account: str | None = None,
) -> dict:
    """Read one note's full content by stable id or title."""
    if not title and not note_id:
        raise RuntimeError("Provide title or note_id")
    try:
        row = _parse_json(run_applescript(_READ_SCRIPT, note_id or "", title or "", account or "", timeout=30))
    except RuntimeError:
        # AppleScript plain-text read is the canonical path. NoteStore is only
        # for recovery from large-note timeout/failure cases.
        store_note = _read_note_from_store(title=title, note_id=note_id, account=account)
        if store_note is not None:
            return store_note
        raise
    if not isinstance(row, dict):
        raise RuntimeError("Note not found")
    return _normalize_note(row)


@mcp.tool(annotations=ToolAnnotations(title="Create Note"))
def notes_create(
    folder: str,
    title: str,
    body: str,
    account: str | None = None,
) -> dict:
    """Create a note in a folder."""
    row = _parse_json(run_applescript(_CREATE_SCRIPT, folder, title, body, account or "", timeout=30))
    if not isinstance(row, dict):
        raise RuntimeError("Unexpected create note payload")
    note = _normalize_note(row)
    return {"id": note.get("id"), "title": note.get("title"), "success": True}


@mcp.tool(annotations=ToolAnnotations(title="Append Note"))
def notes_append(
    text: str,
    title: str | None = None,
    note_id: str | None = None,
    account: str | None = None,
) -> dict:
    """Append text to a note by stable id or title."""
    if not title and not note_id:
        raise RuntimeError("Provide title or note_id")
    row = _parse_json(run_applescript(_APPEND_SCRIPT, note_id or "", title or "", text, account or "", timeout=30))
    if not isinstance(row, dict):
        raise RuntimeError("Unexpected append note payload")
    note = _normalize_note(row)
    return {"id": note.get("id"), "title": note.get("title"), "success": True}


@mcp.tool(annotations=ToolAnnotations(title="Delete Note", destructiveHint=True))
def notes_delete(
    title: str | None = None,
    note_id: str | None = None,
    account: str | None = None,
    confirm: bool = False,
) -> dict:
    """Delete a note by stable id or title. Requires confirm=True."""
    if not title and not note_id:
        raise RuntimeError("Provide title or note_id")
    if not confirm:
        try:
            preview = notes_read(title=title, note_id=note_id, account=account)
            label = preview.get("title") or note_id or title
        except RuntimeError:
            label = note_id or title
        return {"preview": f"Would delete note: {label}", "confirmed": False}
    row = _parse_json(run_applescript(_DELETE_SCRIPT, note_id or "", title or "", account or "", timeout=30))
    if not isinstance(row, dict):
        raise RuntimeError("Unexpected delete note payload")
    return {"id": row.get("id") or note_id, "success": True}
