from __future__ import annotations

import json
from datetime import datetime

from mcp.types import ToolAnnotations

from ..bridge import run_applescript
from ..server import mcp


def _nn(value):
    if value is None:
        return None
    if isinstance(value, str) and (value == "" or value == "missing value"):
        return None
    return value


def _validate_iso(due: str) -> str:
    try:
        datetime.fromisoformat(due)
    except ValueError as e:
        raise RuntimeError(f"Invalid ISO 8601 datetime: {due}") from e
    return due


_LISTS_SCRIPT = r"""
on run argv
    tell application "Reminders"
        set out to {}
        repeat with l in lists
            set end of out to name of l
        end repeat
    end tell
    return my jarr(out)
end run

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


_LIST_SCRIPT = r"""
on run argv
    set list_name to item 1 of argv
    set completed_flag to item 2 of argv
    set want_completed to (completed_flag is "true")
    set rows to {}
    tell application "Reminders"
        if list_name is "" then
            set target_reminders to reminders
        else
            set target_list to list list_name
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
                try
                    set rlist to name of container of r
                end try
                set end of rows to {rid, rtitle, rnotes, rdue, rprio, rlist, is_done}
            end if
        end repeat
    end tell
    return my jsonify(rows)
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
        if (item 7 of r) then set done_str to "true"
        set prio_str to (item 5 of r) as string
        set out to out & "{" & ¬
            "\"id\":" & my jstr(item 1 of r) & "," & ¬
            "\"title\":" & my jstr(item 2 of r) & "," & ¬
            "\"notes\":" & my jstr(item 3 of r) & "," & ¬
            "\"due\":" & my jstr(item 4 of r) & "," & ¬
            "\"priority\":" & prio_str & "," & ¬
            "\"list_name\":" & my jstr(item 6 of r) & "," & ¬
            "\"completed\":" & done_str & "}"
    end repeat
    set out to out & "]"
    return out
end jsonify

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


_CREATE_SCRIPT = r"""
on run argv
    set r_title to item 1 of argv
    set r_list to item 2 of argv
    set r_due to item 3 of argv
    set r_notes to item 4 of argv
    set r_prio to (item 5 of argv) as integer
    tell application "Reminders"
        set target_list to list r_list
        set props to {name:r_title}
        if r_notes is not "" then set props to props & {body:r_notes}
        if r_prio is not 0 then set props to props & {priority:r_prio}
        set new_r to make new reminder at end of reminders of target_list with properties props
        if r_due is not "" then
            set due date of new_r to my parse_iso(r_due)
        end if
        set rid to id of new_r
    end tell
    return rid
end run

on parse_iso(s)
    -- Parse "YYYY-MM-DDTHH:MM:SS" into AppleScript date
    set the_date to current date
    set year of the_date to (text 1 thru 4 of s) as integer
    set month of the_date to (text 6 thru 7 of s) as integer
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


_COMPLETE_SCRIPT = r"""
on run argv
    set rid to item 1 of argv
    tell application "Reminders"
        set r to first reminder whose id is rid
        set completed of r to true
    end tell
    return rid
end run
"""


_DELETE_SCRIPT = r"""
on run argv
    set rid to item 1 of argv
    tell application "Reminders"
        set r to first reminder whose id is rid
        delete r
    end tell
    return rid
end run
"""


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def reminders_lists() -> list[str]:
    """List all reminder lists."""
    raw = run_applescript(_LISTS_SCRIPT)
    try:
        parsed = json.loads(raw) if raw else []
    except json.JSONDecodeError as e:
        raise RuntimeError("Failed to parse Reminders lists response") from e
    return [str(n) for n in parsed if _nn(n)]


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
def reminders_list(list_name: str | None = None, completed: bool = False) -> list[dict]:
    """List reminders, optionally filtered by list or status."""
    raw = run_applescript(
        _LIST_SCRIPT,
        list_name or "",
        "true" if completed else "false",
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
                "completed": bool(row.get("completed")),
            }
        )
    return results


@mcp.tool()
def reminders_create(
    title: str,
    list_name: str = "Reminders",
    due: str | None = None,
    notes: str | None = None,
    priority: int = 0,
) -> dict:
    """Create a reminder."""
    due_str = ""
    if due:
        due_str = _validate_iso(due)
    rid = run_applescript(
        _CREATE_SCRIPT,
        title,
        list_name,
        due_str,
        notes or "",
        str(int(priority)),
    )
    return {"id": rid, "success": True}


@mcp.tool()
def reminders_complete(reminder_id: str) -> dict:
    """Mark a reminder as complete."""
    rid = run_applescript(_COMPLETE_SCRIPT, reminder_id)
    return {"id": rid or reminder_id, "success": True}


@mcp.tool(annotations=ToolAnnotations(destructiveHint=True))
def reminders_delete(reminder_id: str) -> dict:
    """Delete a reminder."""
    rid = run_applescript(_DELETE_SCRIPT, reminder_id)
    return {"id": rid or reminder_id, "success": True}
