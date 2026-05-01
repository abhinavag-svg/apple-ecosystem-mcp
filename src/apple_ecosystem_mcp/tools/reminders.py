from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from mcp.types import ToolAnnotations

from ..bridge import run_applescript
from ..server import mcp

_PERMISSION_DENIED_SENTINEL = "__APPLE_ECOSYSTEM_MCP_REMINDERS_PERMISSION_DENIED__"
_PERMISSION_DENIED_MESSAGE = (
    "Permission denied: Reminders automation is not authorized. Grant access in "
    "System Settings > Privacy & Security > Automation, then retry."
)


def _is_permission_error_message(message: str) -> bool:
    lowered = message.lower()
    return (
        "-1743" in message
        or "not authorized" in lowered
        or "not authorised" in lowered
        or "not allowed to send apple events" in lowered
    )


def _run_reminders_script(script: str, args: tuple[str, ...] = ()) -> str:
    try:
        raw = run_applescript(script, *args)
    except RuntimeError as e:
        if _is_permission_error_message(str(e)):
            raise RuntimeError(_PERMISSION_DENIED_MESSAGE) from e
        raise
    if raw == _PERMISSION_DENIED_SENTINEL:
        raise RuntimeError(_PERMISSION_DENIED_MESSAGE)
    return raw


def _nn(value):
    if value is None:
        return None
    if isinstance(value, str) and (value == "" or value == "missing value"):
        return None
    return value


def _normalize_due_iso(due: str) -> str:
    """Normalize ISO 8601 input into local naive `YYYY-MM-DDTHH:MM:SS` for AppleScript."""
    if due.endswith("Z"):
        due = due[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(due)
    except ValueError as e:
        raise RuntimeError(f"Invalid ISO 8601 datetime: {due}") from e
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    # AppleScript parser expects seconds.
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


_PERMISSION_HELPERS = r"""
on permission_denied_marker()
    return "__APPLE_ECOSYSTEM_MCP_REMINDERS_PERMISSION_DENIED__"
end permission_denied_marker

on is_permission_error(errMsg, errNum)
    if errNum is -1743 then return true
    set msg to errMsg as string
    if msg contains "not authorized" then return true
    if msg contains "not authorised" then return true
    if msg contains "not allowed to send Apple events" then return true
    if msg contains "Not authorized" then return true
    if msg contains "Not authorised" then return true
    return false
end is_permission_error
"""


_LISTS_SCRIPT = _PERMISSION_HELPERS + r"""
on run argv
    try
        tell application "Reminders"
            set out to {}
            repeat with l in lists
                set lid to ""
                try
                    set lid to id of l
                end try
                set end of out to {lid, name of l}
            end repeat
        end tell
        return my jsonify(out)
    on error errMsg number errNum
        if my is_permission_error(errMsg, errNum) then return my permission_denied_marker()
        error errMsg number errNum
    end try
end run

on jsonify(rows)
    set s to "["
    set first_item to true
    repeat with r in rows
        if first_item then
            set first_item to false
        else
            set s to s & ","
        end if
        set s to s & "{\"id\":" & my jstr(item 1 of r) & ",\"name\":" & my jstr(item 2 of r) & "}"
    end repeat
    set s to s & "]"
    return s
end jsonify

on jstr(v)
    try
        if v is missing value then return "null"
    end try
    set s to v as string
    if s = "" then return "\"\""
    set s to my replace(s, "\\", "\\\\")
    set s to my replace(s, "\"", "\\\"")
    return "\"" & s & "\""
end jstr

on replace(s, f, r)
    set AppleScript's text item delimiters to f
    set parts to text items of s
    set AppleScript's text item delimiters to r
    set out to parts as string
    set AppleScript's text item delimiters to ""
    return out
end replace
"""


_LIST_SCRIPT = _PERMISSION_HELPERS + r"""
on run argv
    set list_id to item 1 of argv
    set list_name to item 2 of argv
    set completed_flag to item 3 of argv
    set want_completed to (completed_flag is "true")
    set rows to {}
    try
        tell application "Reminders"
            if list_id is "" and list_name is "" then
                set target_reminders to reminders
            else
                set target_list to missing value
                repeat with l in lists
                    set current_id to ""
                    try
                        set current_id to id of l
                    end try
                    if list_id is not "" then
                        if (current_id as string) is list_id then
                            set target_list to l
                            exit repeat
                        end if
                    else if (name of l as string) is list_name then
                        set target_list to l
                        exit repeat
                    end if
                end repeat
                if target_list is missing value then
                    return "[]"
                end if
                set target_reminders to reminders of target_list
            end if
            repeat with r in target_reminders
                set is_done to completed of r
                if (want_completed and is_done) or ((not want_completed) and (not is_done)) then
                    set rid to id of r
                    set rtitle to name of r
                    set rnotes to ""
                    try
                        set rnotes to body of r
                    end try
                    set rdue to ""
                    try
                        set rdue to (due date of r) as «class isot» as string
                    end try
                    set rprio to 0
                    try
                        set rprio to priority of r
                    end try
                    set rlist to ""
                    set rlist_id to ""
                    try
                        set rlist to name of container of r
                        set rlist_id to id of container of r
                    end try
                    set rrecur to ""
                    try
                        set rrecur to recurrence of r
                    end try
                    set rtags to {}
                    try
                        repeat with t in tags of r
                            try
                                set end of rtags to name of t
                            on error
                                set end of rtags to t as string
                            end try
                        end repeat
                    end try
                    set end of rows to {rid, rtitle, rnotes, rdue, rprio, rlist, rlist_id, is_done, rrecur, rtags}
                end if
            end repeat
        end tell
        return my jsonify(rows)
    on error errMsg number errNum
        if my is_permission_error(errMsg, errNum) then return my permission_denied_marker()
        error errMsg number errNum
    end try
end run

on jsonify(rows)
    set out to "["
    set first_row to true
    repeat with r in rows
        if first_row then
            set first_row to false
        else
            set out to out & ","
        end if
        set done_str to "false"
        if (item 8 of r) then set done_str to "true"
        set prio_str to (item 5 of r) as string
        set out to out & "{" & ¬
            "\"id\":" & my jstr(item 1 of r) & "," & ¬
            "\"title\":" & my jstr(item 2 of r) & "," & ¬
            "\"notes\":" & my jstr(item 3 of r) & "," & ¬
            "\"due\":" & my jstr(item 4 of r) & "," & ¬
            "\"priority\":" & prio_str & "," & ¬
            "\"list_name\":" & my jstr(item 6 of r) & "," & ¬
            "\"list_id\":" & my jstr(item 7 of r) & "," & ¬
            "\"recurrence\":" & my jstr(item 9 of r) & "," & ¬
            "\"tags\":" & my jarr(item 10 of r) & "," & ¬
            "\"completed\":" & done_str & "}"
    end repeat
    set out to out & "]"
    return out
end jsonify

on jarr(xs)
    set s to "["
    set first_item to true
    repeat with x in xs
        if first_item then
            set first_item to false
        else
            set s to s & ","
        end if
        set s to s & my jstr(x)
    end repeat
    set s to s & "]"
    return s
end jarr

on jstr(v)
    try
        if v is missing value then return "null"
    end try
    set s to v as string
    if s = "" then return "\"\""
    set s to my replace(s, "\\", "\\\\")
    set s to my replace(s, "\"", "\\\"")
    set s to my replace(s, return, "\\n")
    set s to my replace(s, linefeed, "\\n")
    set s to my replace(s, tab, "\\t")
    return "\"" & s & "\""
end jstr

on replace(s, f, r)
    set AppleScript's text item delimiters to f
    set parts to text items of s
    set AppleScript's text item delimiters to r
    set out to parts as string
    set AppleScript's text item delimiters to ""
    return out
end replace
"""


_CREATE_SCRIPT = _PERMISSION_HELPERS + r"""
on run argv
    set r_title to item 1 of argv
    set r_list_id to item 2 of argv
    set r_list to item 3 of argv
    set r_due to item 4 of argv
    set r_notes to item 5 of argv
    set r_prio to (item 6 of argv) as integer
    try
        tell application "Reminders"
            set target_list to missing value
            if r_list_id is "" and r_list is "" then
                if (count of lists) = 0 then error "No reminder lists available" number 404
                set target_list to item 1 of lists
            else
                repeat with l in lists
                    set current_id to ""
                    try
                        set current_id to id of l
                    end try
                    if r_list_id is not "" then
                        if (current_id as string) is r_list_id then
                            set target_list to l
                            exit repeat
                        end if
                    else if (name of l as string) is r_list then
                        set target_list to l
                        exit repeat
                    end if
                end repeat
            end if
            if target_list is missing value then error "List not found" number 404

            set props to {name:r_title}
            if r_notes is not "" then set body of props to r_notes
            if r_prio is not 0 then set priority of props to r_prio
            set new_r to make new reminder at end of reminders of target_list with properties props
            if r_due is not "" then
                set due date of new_r to my parse_iso(r_due)
            end if
            set rid to id of new_r
        end tell
        return rid
    on error errMsg number errNum
        if my is_permission_error(errMsg, errNum) then return my permission_denied_marker()
        error errMsg number errNum
    end try
end run

on parse_iso(s)
    -- Parse "YYYY-MM-DDTHH:MM:SS" into an AppleScript date in local time.
    set the_date to current date
    set year of the_date to (text 1 thru 4 of s) as integer
    set monthNum to (text 6 thru 7 of s) as integer
    set months to {January, February, March, April, May, June, July, August, September, October, November, December}
    set month of the_date to item monthNum of months
    set day of the_date to (text 9 thru 10 of s) as integer
    if (count of s) >= 19 then
        set hours of the_date to (text 12 thru 13 of s) as integer
        set minutes of the_date to (text 15 thru 16 of s) as integer
        set seconds of the_date to (text 18 thru 19 of s) as integer
    else
        set hours of the_date to 0
        set minutes of the_date to 0
        set seconds of the_date to 0
    end if
    return the_date
end parse_iso
"""


_COMPLETE_SCRIPT = _PERMISSION_HELPERS + r"""
on run argv
    set rid to item 1 of argv
    try
        tell application "Reminders"
            set r to first reminder whose id is rid
            set completed of r to true
        end tell
        return rid
    on error errMsg number errNum
        if my is_permission_error(errMsg, errNum) then return my permission_denied_marker()
        error errMsg number errNum
    end try
end run
"""


_DELETE_SCRIPT = _PERMISSION_HELPERS + r"""
on run argv
    set rid to item 1 of argv
    try
        tell application "Reminders"
            set r to first reminder whose id is rid
            delete r
        end tell
        return rid
    on error errMsg number errNum
        if my is_permission_error(errMsg, errNum) then return my permission_denied_marker()
        error errMsg number errNum
    end try
end run
"""


@mcp.tool(annotations=ToolAnnotations(title="List Reminder Lists", readOnlyHint=True))
def reminders_lists(include_metadata: bool = False) -> list[Any]:
    """List reminder lists.

    By default this preserves the original list-of-names response. Set
    include_metadata=True to get stable list identifiers for targeting.
    """
    raw = _run_reminders_script(_LISTS_SCRIPT)
    try:
        parsed = json.loads(raw) if raw else []
    except json.JSONDecodeError as e:
        raise RuntimeError("Failed to parse Reminders lists response") from e

    lists: list[dict] = []
    for row in parsed:
        if isinstance(row, dict):
            name = _nn(row.get("name"))
            if not name:
                continue
            lists.append({"id": _nn(row.get("id")), "name": str(name)})
        else:
            name = _nn(row)
            if name:
                lists.append({"id": None, "name": str(name)})

    if include_metadata:
        return lists
    return [item["name"] for item in lists]


@mcp.tool(annotations=ToolAnnotations(title="List Reminders", readOnlyHint=True))
def reminders_list(
    list_name: str | None = None,
    completed: bool = False,
    reminders_list_id: str | None = None,
) -> list[dict]:
    """List reminders, optionally filtered by stable list id, list name, or status."""
    raw = _run_reminders_script(
        _LIST_SCRIPT,
        (
            reminders_list_id or "",
            list_name or "",
            "true" if completed else "false",
        ),
    )
    try:
        parsed = json.loads(raw) if raw else []
    except json.JSONDecodeError as e:
        raise RuntimeError("Failed to parse Reminders list response") from e

    results: list[dict] = []
    for row in parsed:
        results.append(
            {
                "id": row.get("id"),
                "title": _nn(row.get("title")),
                "notes": _nn(row.get("notes")),
                "due": _nn(row.get("due")),
                "priority": int(row.get("priority") or 0),
                "list_name": _nn(row.get("list_name")),
                "list_id": _nn(row.get("list_id")),
                "recurrence": _nn(row.get("recurrence")),
                "tags": [str(t) for t in (row.get("tags") or []) if _nn(t)],
                "completed": bool(row.get("completed")),
            }
        )
    return results


@mcp.tool(annotations=ToolAnnotations(title="Create Reminder"))
def reminders_create(
    title: str,
    list_name: str | None = None,
    due: str | None = None,
    notes: str | None = None,
    priority: int = 0,
    reminders_list_id: str | None = None,
) -> dict:
    """Create a reminder."""
    if list_name and not reminders_list_id:
        try:
            known = reminders_lists()
        except RuntimeError:
            known = []
        if known and list_name not in known:
            raise RuntimeError(
                f"Unknown Reminders list: {list_name}. Call reminders_lists() to view available lists."
            )

    due_str = ""
    if due:
        due_str = _normalize_due_iso(due)
    priority = max(0, min(int(priority), 9))
    rid = _run_reminders_script(
        _CREATE_SCRIPT,
        (
            title,
            reminders_list_id or "",
            list_name or "",
            due_str,
            notes or "",
            str(priority),
        ),
    )
    return {"id": rid, "success": True}


@mcp.tool(annotations=ToolAnnotations(title="Complete Reminder", destructiveHint=True))
def reminders_complete(reminder_id: str) -> dict:
    """Mark a reminder as complete."""
    rid = _run_reminders_script(_COMPLETE_SCRIPT, (reminder_id,))
    return {"id": rid or reminder_id, "success": True}


@mcp.tool(annotations=ToolAnnotations(title="Delete Reminder", destructiveHint=True))
def reminders_delete(reminder_id: str) -> dict:
    """Delete a reminder."""
    rid = _run_reminders_script(_DELETE_SCRIPT, (reminder_id,))
    return {"id": rid or reminder_id, "success": True}
