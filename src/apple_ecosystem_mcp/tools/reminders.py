from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from mcp.types import ToolAnnotations

from ..bridge import run_applescript, cache_inventory
from ..native_provider import NativeProviderUnavailable, try_native
from ..preferences import PreferencesStore
from ..resolver import ResolverError, resolve_target
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


def _run_reminders_script(script: str, args: tuple[str, ...] = (), *, timeout: int = 35) -> str:
    try:
        raw = run_applescript(script, *args, timeout=timeout)
    except RuntimeError as e:
        if _is_permission_error_message(str(e)):
            raise RuntimeError(_PERMISSION_DENIED_MESSAGE) from e
        raise
    if raw == _PERMISSION_DENIED_SENTINEL:
        raise RuntimeError(_PERMISSION_DENIED_MESSAGE)
    return raw


def _timeout_payload(list_name: str | None, reminders_list_id: str | None, timeout: int) -> dict[str, Any]:
    return {
        "error": "tool_timeout",
        "tool": "reminders_list",
        "message": "Reminders did not return items before the local timeout.",
        "list_name": list_name,
        "list_id": reminders_list_id,
        "timeout_seconds": timeout,
        "hint": "Try a smaller limit, another list, or use reminders_lists to inspect available lists.",
    }


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


def _native_required_error(tool: str) -> RuntimeError:
    return RuntimeError(f"{tool} requires the bundled native helper")


def _nn(value):
    if value is None:
        return None
    if isinstance(value, str) and (value == "" or value == "missing value"):
        return None
    return value


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
    set lim to (item 4 of argv) as integer
    set scan_lim to (item 5 of argv) as integer
    set want_completed to (completed_flag is "true")
    set rows to {}
    set count_ to 0
    set scanned_ to 0
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
                    else
                        if (name of l as string) is list_name then
                            set target_list to l
                            exit repeat
                        end if
                    end if
                end repeat
                if target_list is missing value then
                    return "[]"
                end if
                set target_reminders to reminders of target_list
            end if
            repeat with r in target_reminders
                if count_ ≥ lim then exit repeat
                if scanned_ ≥ scan_lim then exit repeat
                set scanned_ to scanned_ + 1
                set is_done to completed of r
                if (want_completed and is_done) or ((not want_completed) and (not is_done)) then
                    set count_ to count_ + 1
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
                    set rtags to {}
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
    set s to my replace(s, ASCII character 13, "\\n")
    set s to my replace(s, ASCII character 10, "\\n")
    set s to my replace(s, ASCII character 9, "\\t")
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
                    else
                        if (name of l as string) is r_list then
                            set target_list to l
                            exit repeat
                        end if
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
@cache_inventory("reminders_lists", ttl=30)
def reminders_lists(include_metadata: bool = False) -> list[Any]:
    """List reminder lists.

    By default this preserves the original list-of-names response. Set
    include_metadata=True to get stable list identifiers for targeting.
    """
    try:
        parsed = try_native("reminders", "list-lists", timeout=15)
    except NativeProviderUnavailable:
        parsed = None
    if not isinstance(parsed, list):
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
        normalized: list[dict] = []
        for idx, item in enumerate(lists):
            normalized.append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "kind": "reminder_list",
                    "account_name": _nn(item.get("account_name")),
                    "path": _nn(item.get("path")),
                    "writable": item.get("writable"),
                    "default_candidate": idx == 0,
                }
            )
        return normalized
    return [item["name"] for item in lists]


@mcp.tool(annotations=ToolAnnotations(title="List Reminders", readOnlyHint=True))
def reminders_list(
    list_name: str | None = None,
    completed: bool = False,
    reminders_list_id: str | None = None,
    limit: int = 20,
) -> list[dict] | dict:
    """List reminders from a specific list. Always requires list_name or reminders_list_id.

    If neither is provided, returns the available reminder lists and asks the user
    to pick one — never attempts to enumerate all reminders across all lists.
    limit: max reminders to return (default 20, max 100).
    """
    if not list_name and not reminders_list_id:
        available = reminders_lists(include_metadata=True)
        return {
            "action_required": "Please specify which list to query",
            "available_lists": available,
            "hint": "Call reminders_list again with list_name=<name> from the list above",
        }
    capped = max(1, min(int(limit), 100))
    try:
        parsed = try_native(
            "reminders",
            "list-reminders",
            {
                "list_name": list_name or "",
                "reminders_list_id": reminders_list_id or "",
                "completed": completed,
                "limit": capped,
            },
            timeout=20,
        )
    except NativeProviderUnavailable:
        parsed = None
    if not isinstance(parsed, list):
        parsed = None
    if parsed is None:
        parsed = _reminders_list_applescript(list_name, completed, reminders_list_id, capped)
    if isinstance(parsed, dict):
        return parsed

    return _normalize_reminder_rows(parsed)


def _reminders_list_applescript(
    list_name: str | None,
    completed: bool,
    reminders_list_id: str | None,
    capped: int,
) -> list[dict] | dict:
    scan_limit = max(capped, min(capped * 3, 60))
    timeout_seconds = 10
    try:
        raw = _run_reminders_script(
            _LIST_SCRIPT,
            (
                reminders_list_id or "",
                list_name or "",
                "true" if completed else "false",
                str(capped),
                str(scan_limit),
            ),
            timeout=timeout_seconds,
        )
    except RuntimeError as e:
        if str(e) == "AppleScript timed out":
            return _timeout_payload(list_name, reminders_list_id, timeout_seconds)
        raise
    try:
        parsed = json.loads(raw) if raw else []
    except json.JSONDecodeError as e:
        raise RuntimeError("Failed to parse Reminders list response") from e
    return parsed


def _normalize_reminder_rows(parsed: list[dict]) -> list[dict]:
    results: list[dict] = []
    for row in parsed:
        if not isinstance(row, dict):
            continue
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


def _resolve_reminder_list_target(
    list_name: str | None = None,
    reminders_list_id: str | None = None,
) -> tuple[str | None, str | None] | dict:
    if not list_name and not reminders_list_id:
        return {
            "error": "missing_target",
            "message": "Provide list_name or reminders_list_id",
            "scope": "reminder_list",
        }
    try:
        resolved = resolve_target(
            reminders_list_id or list_name,
            reminders_lists(include_metadata=True),
            scope="reminder_list",
            preferences=PreferencesStore(),
        )
    except ResolverError as exc:
        return exc.to_dict()
    return _nn(resolved.item.get("id")), _nn(resolved.item.get("name"))


@mcp.tool(annotations=ToolAnnotations(title="Create Reminder List"))
def reminders_create_list(name: str) -> dict:
    """Create a reminder list."""
    try:
        data = try_native("reminders", "create-list", {"name": name}, timeout=15)
    except NativeProviderUnavailable as exc:
        raise _native_required_error("reminders_create_list") from exc
    if not isinstance(data, dict) or not data.get("id"):
        raise RuntimeError("Unexpected create reminder list payload")
    return {"id": data["id"], "name": data.get("name") or name, "success": True}


@mcp.tool(annotations=ToolAnnotations(title="Rename Reminder List"))
def reminders_rename_list(
    new_name: str,
    list_name: str | None = None,
    reminders_list_id: str | None = None,
) -> dict:
    """Rename a reminder list by stable id or friendly name."""
    resolved = _resolve_reminder_list_target(list_name, reminders_list_id)
    if isinstance(resolved, dict):
        return resolved
    resolved_id, resolved_name = resolved
    try:
        data = try_native(
            "reminders",
            "rename-list",
            {
                "reminders_list_id": resolved_id or "",
                "old_name": resolved_name or list_name or "",
                "new_name": new_name,
            },
            timeout=15,
        )
    except NativeProviderUnavailable as exc:
        raise _native_required_error("reminders_rename_list") from exc
    if not isinstance(data, dict) or not data.get("id"):
        raise RuntimeError("Unexpected rename reminder list payload")
    return {"id": data["id"], "name": data.get("name") or new_name, "success": True}


@mcp.tool(annotations=ToolAnnotations(title="Delete Reminder List", destructiveHint=True))
def reminders_delete_list(
    list_name: str | None = None,
    reminders_list_id: str | None = None,
    confirm: bool = False,
) -> dict:
    """Delete a reminder list. Requires confirm=True."""
    resolved = _resolve_reminder_list_target(list_name, reminders_list_id)
    if isinstance(resolved, dict):
        return resolved
    resolved_id, resolved_name = resolved
    label = resolved_name or list_name or reminders_list_id
    if not confirm:
        return {"preview": f"Would delete reminder list: {label}", "confirmed": False}
    try:
        data = try_native(
            "reminders",
            "delete-list",
            {"reminders_list_id": resolved_id or "", "name": resolved_name or list_name or ""},
            timeout=15,
        )
    except NativeProviderUnavailable as exc:
        raise _native_required_error("reminders_delete_list") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected delete reminder list payload")
    return {"id": data.get("id") or resolved_id, "success": True}


def _reminders_matching_due(kind: str, limit: int) -> list[dict]:
    capped = max(1, min(int(limit), 100))
    try:
        parsed = try_native(
            "reminders",
            "search",
            {"query": "", "limit": 200, "include_completed": False},
            timeout=20,
        )
    except NativeProviderUnavailable as exc:
        raise _native_required_error(f"reminders_{kind}") from exc
    rows = _normalize_reminder_rows(parsed if isinstance(parsed, list) else [])
    today = datetime.now().date()
    matches: list[dict] = []
    for row in rows:
        due = row.get("due")
        if not due:
            continue
        try:
            due_date = datetime.fromisoformat(str(due)).date()
        except ValueError:
            continue
        if (kind == "today" and due_date == today) or (kind == "overdue" and due_date < today):
            matches.append(row)
    return matches[:capped]


@mcp.tool(annotations=ToolAnnotations(title="Today's Reminders", readOnlyHint=True))
def reminders_today(limit: int = 50) -> list[dict]:
    """Return incomplete reminders due today across all lists."""
    return _reminders_matching_due("today", limit)


@mcp.tool(annotations=ToolAnnotations(title="Overdue Reminders", readOnlyHint=True))
def reminders_overdue(limit: int = 50) -> list[dict]:
    """Return incomplete reminders due before today across all lists."""
    return _reminders_matching_due("overdue", limit)


@mcp.tool(annotations=ToolAnnotations(title="Search Reminders", readOnlyHint=True))
def reminders_search(query: str, limit: int = 50, include_completed: bool = False) -> list[dict]:
    """Search reminders by title or notes across all lists."""
    capped = max(1, min(int(limit), 100))
    try:
        parsed = try_native(
            "reminders",
            "search",
            {"query": query, "limit": capped, "include_completed": include_completed},
            timeout=20,
        )
    except NativeProviderUnavailable as exc:
        raise _native_required_error("reminders_search") from exc
    return _normalize_reminder_rows(parsed if isinstance(parsed, list) else [])


@mcp.tool(annotations=ToolAnnotations(title="Update Reminder"))
def reminders_update(
    reminder_id: str,
    title: str | None = None,
    due: str | None = None,
    notes: str | None = None,
    priority: int | None = None,
    clear_due: bool = False,
    clear_notes: bool = False,
) -> dict:
    """Update a reminder by canonical id."""
    if clear_due and due is not None:
        raise RuntimeError("Use either due or clear_due, not both")
    if clear_notes and notes is not None:
        raise RuntimeError("Use either notes or clear_notes, not both")
    payload: dict[str, Any] = {
        "reminder_id": reminder_id,
        "clear_due": clear_due,
        "clear_notes": clear_notes,
    }
    if title is not None:
        payload["title"] = title
    if due is not None:
        payload["due"] = _normalize_due_iso(due)
    if notes is not None:
        payload["notes"] = notes
    if priority is not None:
        payload["priority"] = max(0, min(int(priority), 9))
    try:
        data = try_native("reminders", "update", payload, timeout=15)
    except NativeProviderUnavailable as exc:
        raise _native_required_error("reminders_update") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected update reminder payload")
    return {"id": data.get("id") or reminder_id, "success": True}


@mcp.tool(annotations=ToolAnnotations(title="Rename Reminder"))
def reminders_rename(reminder_id: str, title: str) -> dict:
    """Rename a reminder by canonical id."""
    return reminders_update(reminder_id, title=title)


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
    preferences = PreferencesStore()
    should_use_default = (
        list_name is None
        and reminders_list_id is None
        and preferences.get_default("reminder_list") is not None
    )
    if list_name is not None or reminders_list_id is not None or should_use_default:
        query = reminders_list_id or list_name
        try:
            resolved = resolve_target(
                query,
                reminders_lists(include_metadata=True),
                scope="reminder_list",
                preferences=preferences,
                use_default=should_use_default,
            )
        except ResolverError as exc:
            return exc.to_dict()
        reminders_list_id = _nn(resolved.item.get("id"))
        list_name = _nn(resolved.item.get("name"))

    due_str = ""
    if due:
        due_str = _normalize_due_iso(due)
    priority = max(0, min(int(priority), 9))
    try:
        data = try_native(
            "reminders",
            "create",
            {
                "title": title,
                "reminders_list_id": reminders_list_id or "",
                "list_name": list_name or "",
                "due": due_str,
                "notes": notes or "",
                "priority": priority,
            },
            timeout=15,
        )
    except NativeProviderUnavailable:
        data = None
    if isinstance(data, dict) and data.get("id"):
        return {"id": data["id"], "success": True}

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
    try:
        data = try_native("reminders", "complete", {"reminder_id": reminder_id}, timeout=15)
    except NativeProviderUnavailable:
        data = None
    if isinstance(data, dict):
        return {"id": data.get("id") or reminder_id, "success": True}

    rid = _run_reminders_script(_COMPLETE_SCRIPT, (reminder_id,))
    return {"id": rid or reminder_id, "success": True}


@mcp.tool(annotations=ToolAnnotations(title="Delete Reminder", destructiveHint=True))
def reminders_delete(reminder_id: str) -> dict:
    """Delete a reminder."""
    try:
        data = try_native("reminders", "delete", {"reminder_id": reminder_id}, timeout=15)
    except NativeProviderUnavailable:
        data = None
    if isinstance(data, dict):
        return {"id": data.get("id") or reminder_id, "success": True}

    rid = _run_reminders_script(_DELETE_SCRIPT, (reminder_id,))
    return {"id": rid or reminder_id, "success": True}
