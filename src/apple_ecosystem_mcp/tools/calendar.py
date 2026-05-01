from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from mcp.types import ToolAnnotations

from ..bridge import run_applescript
from ..server import mcp

# Result-size limits (see Implementation Plan §Result-Size Policy).
LIST_EVENTS_DEFAULT_LIMIT = 50
LIST_EVENTS_MAX_LIMIT = 200


# ---------------------------------------------------------------------------
# AppleScript sources.
#
# All scripts read user input via `on run argv` and never interpolate Python
# strings into the AppleScript source. Structured responses are JSON strings.
# Dates are emitted as ISO 8601 via the `«class isot» as string` coercion.
# ---------------------------------------------------------------------------

# Shared JSON helpers embedded in every script. AppleScript has no native JSON
# encoder; we build strings by hand. The join handler and _json_str helper
# handle newlines, quotes, and backslashes defensively.
_JSON_HELPERS = r"""
on _js(s)
    if s is missing value then return "null"
    set out to ""
    repeat with i from 1 to length of (s as string)
        set ch to character i of (s as string)
        set c to id of ch
        if c is 34 then
            set out to out & "\\\""
        else if c is 92 then
            set out to out & "\\\\"
        else if c is 8 then
            set out to out & "\\b"
        else if c is 9 then
            set out to out & "\\t"
        else if c is 10 then
            set out to out & "\\n"
        else if c is 12 then
            set out to out & "\\f"
        else if c is 13 then
            set out to out & "\\r"
        else if c < 32 then
            set hexch to "0123456789abcdef"
            set hi to (c div 16) + 1
            set lo to (c mod 16) + 1
            set out to out & "\\u00" & character hi of hexch & character lo of hexch
        else
            set out to out & ch
        end if
    end repeat
    return "\"" & out & "\""
end _js

on _bool(v)
    if v is true then
        return "true"
    else
        return "false"
    end if
end _bool

on _iso(d)
    if d is missing value then return "null"
    return "\"" & ((d as «class isot») as string) & "\""
end _iso
"""


_LIST_CALENDARS_SCRIPT = _JSON_HELPERS + r"""
on run argv
    tell application "Calendar"
        set items_ to {}
        repeat with c in calendars
            set n to name of c
            set u to uid of c
            try
                set acct to (name of (account of c))
            on error
                set acct to missing value
            end try
            try
                set w to writable of c
            on error
                set w to true
            end try
            set row to "{\"name\":" & my _js(n) & ",\"uid\":" & my _js(u) & ",\"account_name\":" & my _js(acct) & ",\"writable\":" & my _bool(w) & "}"
            set end of items_ to row
        end repeat
    end tell
    set AppleScript's text item delimiters to ","
    set out to "[" & (items_ as string) & "]"
    set AppleScript's text item delimiters to ""
    return out
end run
"""


_LIST_EVENTS_SCRIPT = _JSON_HELPERS + r"""
on run argv
    set startISO to item 1 of argv
    set endISO to item 2 of argv
    set filterUID to item 3 of argv
    set startDate to my _parseISO(startISO)
    set endDate to my _parseISO(endISO)

    tell application "Calendar"
        set items_ to {}
        repeat with c in calendars
            set cuid to uid of c
            if filterUID is "" or filterUID is cuid then
                try
                    set evs to (every event of c whose start date < endDate and end date > startDate)
                on error
                    set evs to {}
                end try
                repeat with ev in evs
                    set t to summary of ev
                    set u to uid of ev
                    try
                        set loc to location of ev
                    on error
                        set loc to missing value
                    end try
                    try
                        set allday to allday event of ev
                    on error
                        set allday to false
                    end try
                    set sd to start date of ev
                    set ed to end date of ev
                    set invList to {}
                    try
                        repeat with a in (attendees of ev)
                            set addr to missing value
                            try
                                set addr to email of a
                            end try
                            if addr is not missing value and addr is not "" then set end of invList to my _js(addr)
                        end repeat
                    end try
                    set AppleScript's text item delimiters to ","
                    set invJoined to invList as string
                    set AppleScript's text item delimiters to ""
                    set row to "{\"uid\":" & my _js(u) & ",\"title\":" & my _js(t) & ",\"start\":" & my _iso(sd) & ",\"end\":" & my _iso(ed) & ",\"location\":" & my _js(loc) & ",\"all_day\":" & my _bool(allday) & ",\"calendar_uid\":" & my _js(cuid) & ",\"calendar_name\":" & my _js(name of c) & ",\"attendees\":[" & invJoined & "],\"invitees\":[" & invJoined & "]}"
                    set end of items_ to row
                end repeat
            end if
        end repeat
    end tell
    set AppleScript's text item delimiters to ","
    set out to "[" & (items_ as string) & "]"
    set AppleScript's text item delimiters to ""
    return out
end run

on _parseISO(s)
    -- Accept "YYYY-MM-DDTHH:MM:SS" or "YYYY-MM-DD"
    set yr to (text 1 thru 4 of s) as integer
    set mo to (text 6 thru 7 of s) as integer
    set dy to (text 9 thru 10 of s) as integer
    if (length of s) ≥ 19 then
        set hh to (text 12 thru 13 of s) as integer
        set mm to (text 15 thru 16 of s) as integer
        set ss to (text 18 thru 19 of s) as integer
    else
        set hh to 0
        set mm to 0
        set ss to 0
    end if
    set d to current date
    set year of d to yr
    set months to {January, February, March, April, May, June, July, August, September, October, November, December}
    set month of d to item mo of months
    set day of d to dy
    set time of d to hh * 3600 + mm * 60 + ss
    return d
end _parseISO
"""


_GET_EVENT_SCRIPT = _JSON_HELPERS + r"""
on run argv
    set targetUID to item 1 of argv
    tell application "Calendar"
        repeat with c in calendars
            try
                set ev to first event of c whose uid is targetUID
            on error
                set ev to missing value
            end try
            if ev is not missing value then
                set t to summary of ev
                try
                    set loc to location of ev
                on error
                    set loc to missing value
                end try
                try
                    set n to description of ev
                on error
                    set n to missing value
                end try
                try
                    set allday to allday event of ev
                on error
                    set allday to false
                end try
                set sd to start date of ev
                set ed to end date of ev
                set invList to {}
                try
                    repeat with a in (attendees of ev)
                        set addr to missing value
                        try
                            set addr to email of a
                        end try
                        if addr is not missing value and addr is not "" then set end of invList to my _js(addr)
                    end repeat
                end try
                set AppleScript's text item delimiters to ","
                set invJoined to invList as string
                set AppleScript's text item delimiters to ""
                set out to "{\"uid\":" & my _js(targetUID) & ",\"title\":" & my _js(t) & ",\"start\":" & my _iso(sd) & ",\"end\":" & my _iso(ed) & ",\"location\":" & my _js(loc) & ",\"notes\":" & my _js(n) & ",\"all_day\":" & my _bool(allday) & ",\"calendar_uid\":" & my _js(uid of c) & ",\"calendar_name\":" & my _js(name of c) & ",\"attendees\":[" & invJoined & "],\"invitees\":[" & invJoined & "]}"
                return out
            end if
        end repeat
    end tell
    return "null"
end run
"""


_CREATE_EVENT_SCRIPT = _JSON_HELPERS + r"""
on run argv
    set calUID to item 1 of argv
    set titleText to item 2 of argv
    set startISO to item 3 of argv
    set endISO to item 4 of argv
    set loc to item 5 of argv
    set notesText to item 6 of argv
    set inviteesCSV to item 7 of argv

    set startDate to my _parseISO(startISO)
    set endDate to my _parseISO(endISO)

    tell application "Calendar"
        if calUID is "" then
            set targetCal to first calendar whose writable is true
        else
            set targetCal to first calendar whose uid is calUID
        end if
        set props to {summary:titleText, start date:startDate, end date:endDate}
        if loc is not "" then set location of props to loc
        if notesText is not "" then set description of props to notesText
        set newEv to make new event at end of events of targetCal with properties props
        if inviteesCSV is not "" then
            set AppleScript's text item delimiters to ","
            set inviteeList to text items of inviteesCSV
            set AppleScript's text item delimiters to ""
            tell newEv
                repeat with addr in inviteeList
                    try
                        make new attendee at end of attendees with properties {email:addr as string}
                    end try
                end repeat
            end tell
        end if
        set u to uid of newEv
    end tell
    return "{\"uid\":" & my _js(u) & "}"
end run

on _parseISO(s)
    set yr to (text 1 thru 4 of s) as integer
    set mo to (text 6 thru 7 of s) as integer
    set dy to (text 9 thru 10 of s) as integer
    if (length of s) ≥ 19 then
        set hh to (text 12 thru 13 of s) as integer
        set mm to (text 15 thru 16 of s) as integer
        set ss to (text 18 thru 19 of s) as integer
    else
        set hh to 0
        set mm to 0
        set ss to 0
    end if
    set d to current date
    set year of d to yr
    set months to {January, February, March, April, May, June, July, August, September, October, November, December}
    set month of d to item mo of months
    set day of d to dy
    set time of d to hh * 3600 + mm * 60 + ss
    return d
end _parseISO
"""


_UPDATE_EVENT_SCRIPT = _JSON_HELPERS + r"""
on run argv
    set targetUID to item 1 of argv
    set titleText to item 2 of argv
    set startISO to item 3 of argv
    set endISO to item 4 of argv
    set loc to item 5 of argv
    set notesText to item 6 of argv
    set inviteesCSV to item 7 of argv
    set clearLocationFlag to item 8 of argv
    set clearNotesFlag to item 9 of argv

    tell application "Calendar"
        set found to missing value
        repeat with c in calendars
            try
                set ev to first event of c whose uid is targetUID
                set found to ev
                exit repeat
            end try
        end repeat
        if found is missing value then error "event not found"
        if titleText is not "" then set summary of found to titleText
        if startISO is not "" then set start date of found to my _parseISO(startISO)
        if endISO is not "" then set end date of found to my _parseISO(endISO)
        if clearLocationFlag is "true" then
            set location of found to ""
        else if loc is not "" then
            set location of found to loc
        end if
        if clearNotesFlag is "true" then
            set description of found to ""
        else if notesText is not "" then
            set description of found to notesText
        end if
        if inviteesCSV is not "" then
            set AppleScript's text item delimiters to ","
            set inviteeList to text items of inviteesCSV
            set AppleScript's text item delimiters to ""
            set existingEmails to {}
            try
                repeat with a in (attendees of found)
                    try
                        set end of existingEmails to my _lower(email of a)
                    end try
                end repeat
            end try
            tell found
                repeat with addr in inviteeList
                    set addrText to addr as string
                    set addrKey to my _lower(addrText)
                    if existingEmails does not contain addrKey then
                        try
                            make new attendee at end of attendees with properties {email:addrText}
                            set end of existingEmails to addrKey
                        end try
                    end if
                end repeat
            end tell
        end if
    end tell
    return "{\"uid\":" & my _js(targetUID) & "}"
end run

on _parseISO(s)
    set yr to (text 1 thru 4 of s) as integer
    set mo to (text 6 thru 7 of s) as integer
    set dy to (text 9 thru 10 of s) as integer
    if (length of s) ≥ 19 then
        set hh to (text 12 thru 13 of s) as integer
        set mm to (text 15 thru 16 of s) as integer
        set ss to (text 18 thru 19 of s) as integer
    else
        set hh to 0
        set mm to 0
        set ss to 0
    end if
    set d to current date
    set year of d to yr
    set months to {January, February, March, April, May, June, July, August, September, October, November, December}
    set month of d to item mo of months
    set day of d to dy
    set time of d to hh * 3600 + mm * 60 + ss
    return d
end _parseISO

on _lower(s)
    set upperChars to "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    set lowerChars to "abcdefghijklmnopqrstuvwxyz"
    set out to ""
    repeat with i from 1 to length of (s as string)
        set ch to character i of (s as string)
        set p to offset of ch in upperChars
        if p > 0 then
            set out to out & character p of lowerChars
        else
            set out to out & ch
        end if
    end repeat
    return out
end _lower
"""


_DELETE_EVENT_SCRIPT = r"""
on run argv
    set targetUID to item 1 of argv
    tell application "Calendar"
        repeat with c in calendars
            try
                set ev to first event of c whose uid is targetUID
                delete ev
                return "ok"
            end try
        end repeat
    end tell
    error "event not found"
end run
"""


# ---------------------------------------------------------------------------
# Python helpers
# ---------------------------------------------------------------------------


def _parse_iso(value: str) -> datetime:
    """Parse ISO 8601 — raise a sanitized RuntimeError on failure."""
    try:
        # fromisoformat accepts "YYYY-MM-DD" and "YYYY-MM-DDTHH:MM:SS".
        return datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Invalid ISO 8601 datetime") from exc


def _parse_json(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("AppleScript returned invalid JSON") from exc


def _normalize_calendar_iso(value: str) -> str:
    """Normalize ISO inputs to local naive datetimes for AppleScript.

    Contract: callers may pass YYYY-MM-DD, local naive datetimes, or datetimes
    with an offset / trailing Z. Offset-aware values are converted to the
    machine's local timezone and stripped of tzinfo because Calendar
    AppleScript date construction uses local date components.
    """
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = _parse_iso(value)
    if dt.tzinfo is not None:
        dt = dt.astimezone().replace(tzinfo=None)
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _dedupe_emails(emails: list[str] | None) -> list[str]:
    if not emails:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for email in emails:
        normalized = email.strip()
        if not normalized:
            continue
        key = normalized.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(normalized)
    return out


def _with_attendees_alias(record: dict) -> dict:
    if "attendees" not in record and "invitees" in record:
        record["attendees"] = record["invitees"]
    if "invitees" not in record and "attendees" in record:
        record["invitees"] = record["attendees"]
    return record


def _calendars_cached() -> list[dict]:
    raw = run_applescript(_LIST_CALENDARS_SCRIPT)
    data = _parse_json(raw)
    if not isinstance(data, list):
        raise RuntimeError("Unexpected calendars payload")
    return data


def _require_writable_uid(calendar_uid: str | None) -> None:
    """Reject non-writable calendar_uid (for create/update).

    Passing ``None`` is allowed — the AppleScript create path falls back to the
    first writable calendar.
    """
    if calendar_uid is None:
        return
    for cal in _calendars_cached():
        if cal.get("uid") == calendar_uid:
            if not cal.get("writable", False):
                raise RuntimeError("Calendar is not writable")
            return
    raise RuntimeError("Calendar not found")


def _merge_intervals(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    if not intervals:
        return []
    sorted_iv = sorted(intervals, key=lambda x: x[0])
    merged: list[tuple[datetime, datetime]] = [sorted_iv[0]]
    for start, end in sorted_iv[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool(annotations=ToolAnnotations(title="List Calendars", readOnlyHint=True))
def calendar_list_calendars() -> list[dict]:
    """List calendars across all accounts with uid, account_name, and writable."""
    return _calendars_cached()


@mcp.tool(annotations=ToolAnnotations(title="List Events", readOnlyHint=True))
def calendar_list_events(
    start: str,
    end: str,
    calendar_uid: str | None = None,
    limit: int = LIST_EVENTS_DEFAULT_LIMIT,
) -> list[dict]:
    """List calendar events overlapping an ISO 8601 time range.

    Inputs with offsets or trailing Z are converted to local naive datetimes
    before they are passed to AppleScript.
    """
    start_norm = _normalize_calendar_iso(start)
    end_norm = _normalize_calendar_iso(end)

    capped = max(1, min(int(limit), LIST_EVENTS_MAX_LIMIT))
    raw = run_applescript(_LIST_EVENTS_SCRIPT, start_norm, end_norm, calendar_uid or "")
    data = _parse_json(raw)
    if not isinstance(data, list):
        raise RuntimeError("Unexpected events payload")
    return [_with_attendees_alias(ev) if isinstance(ev, dict) else ev for ev in data[:capped]]


@mcp.tool(annotations=ToolAnnotations(title="Get Event", readOnlyHint=True))
def calendar_get_event(event_id: str) -> dict:
    """Get details for a specific event by canonical UID."""
    raw = run_applescript(_GET_EVENT_SCRIPT, event_id)
    data = _parse_json(raw)
    if data is None:
        raise RuntimeError("Event not found")
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected event payload")
    return _with_attendees_alias(data)


@mcp.tool(annotations=ToolAnnotations(title="Create Event"))
def calendar_create_event(
    title: str,
    start: str,
    end: str,
    calendar_uid: str | None = None,
    location: str | None = None,
    notes: str | None = None,
    invitees: list[str] | None = None,
) -> dict:
    """Create a calendar event; rejects non-writable calendars.

    Inputs with offsets or trailing Z are converted to local naive datetimes
    before they are passed to AppleScript.
    """
    start_norm = _normalize_calendar_iso(start)
    end_norm = _normalize_calendar_iso(end)
    _require_writable_uid(calendar_uid)

    invitees_csv = ",".join(_dedupe_emails(invitees))
    raw = run_applescript(
        _CREATE_EVENT_SCRIPT,
        calendar_uid or "",
        title,
        start_norm,
        end_norm,
        location or "",
        notes or "",
        invitees_csv,
    )
    data = _parse_json(raw)
    if not isinstance(data, dict) or "uid" not in data:
        raise RuntimeError("Unexpected create payload")
    return {"uid": data["uid"], "success": True}


@mcp.tool(annotations=ToolAnnotations(title="Update Event"))
def calendar_update_event(
    event_id: str,
    title: str | None = None,
    start: str | None = None,
    end: str | None = None,
    location: str | None = None,
    notes: str | None = None,
    invitees: list[str] | None = None,
    attendees: list[str] | None = None,
    clear_location: bool = False,
    clear_notes: bool = False,
) -> dict:
    """Update an existing event by UID (only provided fields are changed).

    ``clear_location`` and ``clear_notes`` explicitly blank those fields.
    ``attendees`` is accepted as an alias for the older ``invitees`` parameter;
    new attendees are de-duplicated before AppleScript sees them.
    """
    start_norm = ""
    if start is not None:
        start_norm = _normalize_calendar_iso(start)
    end_norm = ""
    if end is not None:
        end_norm = _normalize_calendar_iso(end)
    if clear_location and location is not None:
        raise RuntimeError("Use either location or clear_location, not both")
    if clear_notes and notes is not None:
        raise RuntimeError("Use either notes or clear_notes, not both")
    if invitees is not None and attendees is not None:
        raise RuntimeError("Use either invitees or attendees, not both")

    # Writable check: locate the event's calendar via get_event so we refuse
    # edits on read-only calendars. Cheap because the AppleScript scans already.
    current = run_applescript(_GET_EVENT_SCRIPT, event_id)
    current_data = _parse_json(current)
    if current_data is None:
        raise RuntimeError("Event not found")
    cal_uid = current_data.get("calendar_uid") if isinstance(current_data, dict) else None
    _require_writable_uid(cal_uid)

    attendee_values = attendees if attendees is not None else invitees
    invitees_csv = ",".join(_dedupe_emails(attendee_values))
    raw = run_applescript(
        _UPDATE_EVENT_SCRIPT,
        event_id,
        title or "",
        start_norm,
        end_norm,
        location or "",
        notes or "",
        invitees_csv,
        "true" if clear_location else "false",
        "true" if clear_notes else "false",
    )
    data = _parse_json(raw)
    if not isinstance(data, dict) or "uid" not in data:
        raise RuntimeError("Unexpected update payload")
    return {"uid": data["uid"], "success": True}


@mcp.tool(annotations=ToolAnnotations(title="Delete Event", destructiveHint=True))
def calendar_delete_event(event_id: str, confirm: bool = False) -> dict:
    """Delete an event by UID. Requires confirm=True; otherwise returns a preview."""
    if not confirm:
        try:
            preview_raw = run_applescript(_GET_EVENT_SCRIPT, event_id)
            preview_data = _parse_json(preview_raw)
            title = (
                preview_data.get("title")
                if isinstance(preview_data, dict)
                else None
            )
        except RuntimeError:
            title = None
        label = title or event_id
        return {
            "preview": f"Would delete: {label}",
            "confirmed": False,
        }

    run_applescript(_DELETE_EVENT_SCRIPT, event_id)
    return {"uid": event_id, "success": True}


@mcp.tool(annotations=ToolAnnotations(title="Find Free Time", readOnlyHint=True))
def calendar_find_free_time(
    date: str,
    duration_minutes: int,
    working_hours_start: int = 9,
    working_hours_end: int = 18,
) -> list[dict]:
    """Find free slots on a given day within working hours of at least duration_minutes."""
    if not (0 <= working_hours_start < working_hours_end <= 24):
        raise RuntimeError("Invalid working hours")
    if duration_minutes <= 0:
        raise RuntimeError("duration_minutes must be positive")

    day = datetime.fromisoformat(_normalize_calendar_iso(date)).date()
    window_start = datetime.combine(day, datetime.min.time()).replace(hour=working_hours_start)
    window_end = datetime.combine(day, datetime.min.time()).replace(hour=0) + timedelta(hours=working_hours_end)

    # Query a full-day window so we catch events that start before working hours
    # but end inside them.
    day_start_iso = datetime.combine(day, datetime.min.time()).isoformat()
    day_end_iso = (datetime.combine(day, datetime.min.time()) + timedelta(days=1)).isoformat()
    raw = run_applescript(_LIST_EVENTS_SCRIPT, day_start_iso, day_end_iso, "")
    events = _parse_json(raw) or []
    if not isinstance(events, list):
        raise RuntimeError("Unexpected events payload")

    intervals: list[tuple[datetime, datetime]] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        if ev.get("all_day"):
            # All-day events block the full working window.
            intervals.append((window_start, window_end))
            continue
        s_raw = ev.get("start")
        e_raw = ev.get("end")
        if not s_raw or not e_raw:
            continue
        try:
            s_dt = datetime.fromisoformat(s_raw)
            e_dt = datetime.fromisoformat(e_raw)
        except ValueError:
            continue
        # Clip to working-hours window and drop events fully outside.
        if e_dt <= window_start or s_dt >= window_end:
            continue
        intervals.append((max(s_dt, window_start), min(e_dt, window_end)))

    merged = _merge_intervals(intervals)

    free: list[dict] = []
    cursor = window_start
    for s_dt, e_dt in merged:
        if s_dt > cursor:
            gap = s_dt - cursor
            if gap >= timedelta(minutes=duration_minutes):
                free.append(
                    {
                        "start": cursor.isoformat(),
                        "end": s_dt.isoformat(),
                        "duration_minutes": int(gap.total_seconds() // 60),
                    }
                )
        cursor = max(cursor, e_dt)
    if cursor < window_end:
        gap = window_end - cursor
        if gap >= timedelta(minutes=duration_minutes):
            free.append(
                {
                    "start": cursor.isoformat(),
                    "end": window_end.isoformat(),
                    "duration_minutes": int(gap.total_seconds() // 60),
                }
            )

    return free
