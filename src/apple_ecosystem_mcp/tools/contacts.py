from __future__ import annotations

import json

from mcp.types import ToolAnnotations

from ..bridge import run_applescript
from ..server import mcp

_SEARCH_LIMIT_DEFAULT = 10
_SEARCH_LIMIT_MAX = 50
_NOTES_MAX_CHARS = 2000


def _nn(value):
    """Normalize AppleScript `missing value` sentinels and empties to None."""
    if value is None:
        return None
    if isinstance(value, str):
        if value == "" or value == "missing value":
            return None
    return value


_SEARCH_SCRIPT = r"""
on run argv
    set q to item 1 of argv
    set lim to (item 2 of argv) as integer
    if q is "" then return "[]"
    set output to {}
    tell application "Contacts"
        set count_ to 0
        repeat with p in people
            if count_ ≥ lim then exit repeat
            set pid to id of p
            set pfirst to ""
            try
                set pfirst to first name of p as string
            end try
            set plast to ""
            try
                set plast to last name of p as string
            end try
            set porg to ""
            try
                set porg to organization of p as string
            end try
            set pemail to ""
            try
                if (count of emails of p) > 0 then set pemail to value of first email of p as string
            end try
            set pphone to ""
            try
                if (count of phones of p) > 0 then set pphone to value of first phone of p as string
            end try

            if my containsCI(pfirst, q) or my containsCI(plast, q) or my containsCI((pfirst & " " & plast), q) or my containsCI(porg, q) or my containsCI(pemail, q) or my containsCI(pphone, q) then
                set end of output to {pid, pfirst, plast, pemail, pphone, porg}
                set count_ to count_ + 1
            end if
        end repeat
    end tell
    return my jsonify(output)
end run

on containsCI(hay, needle)
    try
        ignoring case
            return ((hay as string) contains (needle as string))
        end ignoring
    on error
        return false
    end try
end containsCI

on jsonify(rows)
    set out to "["
    set first_row to true
    repeat with r in rows
        if first_row then
            set first_row to false
        else
            set out to out & ","
        end if
        set out to out & "{" & ¬
            "\"id\":" & my jstr(item 1 of r) & "," & ¬
            "\"first\":" & my jstr(item 2 of r) & "," & ¬
            "\"last\":" & my jstr(item 3 of r) & "," & ¬
            "\"email\":" & my jstr(item 4 of r) & "," & ¬
            "\"phone\":" & my jstr(item 5 of r) & "," & ¬
            "\"company\":" & my jstr(item 6 of r) & "}"
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


_GET_SCRIPT = r"""
on run argv
    set cid to item 1 of argv
    tell application "Contacts"
        set p to person id cid
        set pfirst to ""
        try
            set pfirst to first name of p
        end try
        set plast to ""
        try
            set plast to last name of p
        end try
        set porg to ""
        try
            set porg to organization of p
        end try
        set pnote to ""
        try
            set pnote to note of p
        end try
        set pbday to ""
        try
            set pbday to (birth date of p) as «class isot» as string
        end try
        set email_list to {}
        try
            repeat with e in emails of p
                set end of email_list to value of e
            end repeat
        end try
        set phone_list to {}
        try
            repeat with ph in phones of p
                set end of phone_list to value of ph
            end repeat
        end try
        set addr_list to {}
        try
            repeat with a in addresses of p
                set astr to ""
                try
                    set astr to formatted address of a
                end try
                if astr = "" then
                    try
                        set astr to (street of a) & ", " & (city of a)
                    end try
                end if
                set end of addr_list to astr
            end repeat
        end try
    end tell
    set out to "{" & ¬
        "\"id\":" & my jstr(cid) & "," & ¬
        "\"first\":" & my jstr(pfirst) & "," & ¬
        "\"last\":" & my jstr(plast) & "," & ¬
        "\"company\":" & my jstr(porg) & "," & ¬
        "\"notes\":" & my jstr(pnote) & "," & ¬
        "\"birthday\":" & my jstr(pbday) & "," & ¬
        "\"emails\":" & my jarr(email_list) & "," & ¬
        "\"phones\":" & my jarr(phone_list) & "," & ¬
        "\"addresses\":" & my jarr(addr_list) & "}"
    return out
end run

on jarr(xs)
    set out to "["
    set first_item to true
    repeat with x in xs
        if first_item then
            set first_item to false
        else
            set out to out & ","
        end if
        set out to out & my jstr(x)
    end repeat
    set out to out & "]"
    return out
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


_CREATE_SCRIPT = r"""
on run argv
    set pfirst to item 1 of argv
    set plast to item 2 of argv
    set pemail to item 3 of argv
    set pphone to item 4 of argv
    set porg to item 5 of argv
    tell application "Contacts"
        set p to make new person with properties {first name:pfirst}
        if plast is not "" then set last name of p to plast
        if porg is not "" then set organization of p to porg
        if pemail is not "" then
            make new email at end of emails of p with properties {label:"work", value:pemail}
        end if
        if pphone is not "" then
            make new phone at end of phones of p with properties {label:"work", value:pphone}
        end if
        save
        set pid to id of p
    end tell
    return pid
end run
"""


_UPDATE_SCRIPT = r"""
on run argv
    set cid to item 1 of argv
    set pfirst to item 2 of argv
    set plast to item 3 of argv
    set pemail to item 4 of argv
    set pphone to item 5 of argv
    set porg to item 6 of argv
    tell application "Contacts"
        set p to person id cid
        if pfirst is not "__NO_CHANGE__" then set first name of p to pfirst
        if plast is not "__NO_CHANGE__" then set last name of p to plast
        if porg is not "__NO_CHANGE__" then set organization of p to porg
        if pemail is not "__NO_CHANGE__" then
            if (count of emails of p) > 0 then
                set value of first email of p to pemail
            else
                make new email at end of emails of p with properties {label:"work", value:pemail}
            end if
        end if
        if pphone is not "__NO_CHANGE__" then
            if (count of phones of p) > 0 then
                set value of first phone of p to pphone
            else
                make new phone at end of phones of p with properties {label:"work", value:pphone}
            end if
        end if
        save
    end tell
    return cid
end run
"""


_GROUPS_SCRIPT = r"""
on run argv
    tell application "Contacts"
        set out to {}
        repeat with g in groups
            set end of out to name of g
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


@mcp.tool(annotations=ToolAnnotations(title="Search Contacts", readOnlyHint=True))
def contacts_search(query: str, limit: int = _SEARCH_LIMIT_DEFAULT) -> list[dict]:
    """Search contacts by name, email, phone, or company."""
    capped = max(1, min(int(limit), _SEARCH_LIMIT_MAX))
    raw = run_applescript(_SEARCH_SCRIPT, query, str(capped))
    try:
        parsed = json.loads(raw) if raw else []
    except json.JSONDecodeError as e:
        raise RuntimeError("Failed to parse Contacts search response") from e
    results: list[dict] = []
    for row in parsed[:capped]:
        results.append(
            {
                "id": row.get("id"),
                "first": _nn(row.get("first")),
                "last": _nn(row.get("last")),
                "email": _nn(row.get("email")),
                "phone": _nn(row.get("phone")),
                "company": _nn(row.get("company")),
            }
        )
    return results


@mcp.tool(annotations=ToolAnnotations(title="Get Contact", readOnlyHint=True))
def contacts_get(contact_id: str) -> dict:
    """Get a full contact record by id."""
    raw = run_applescript(_GET_SCRIPT, contact_id)
    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError as e:
        raise RuntimeError("Failed to parse Contacts get response") from e

    notes = _nn(data.get("notes")) or ""
    truncated = False
    if len(notes) > _NOTES_MAX_CHARS:
        omitted = len(notes) - _NOTES_MAX_CHARS
        notes = notes[:_NOTES_MAX_CHARS] + f"[truncated — {omitted} chars omitted]"
        truncated = True

    emails = [e for e in (data.get("emails") or []) if _nn(e)]
    phones = [p for p in (data.get("phones") or []) if _nn(p)]
    addresses = [a for a in (data.get("addresses") or []) if _nn(a)]

    result = {
        "id": data.get("id") or contact_id,
        "first": _nn(data.get("first")),
        "last": _nn(data.get("last")),
        "company": _nn(data.get("company")),
        "emails": emails,
        "phones": phones,
        "addresses": addresses,
        "birthday": _nn(data.get("birthday")),
        "notes": notes,
    }
    if truncated:
        result["notes_truncated"] = True
    return result


@mcp.tool(annotations=ToolAnnotations(title="Create Contact"))
def contacts_create(
    first: str,
    last: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    company: str | None = None,
) -> dict:
    """Create a new contact."""
    pid = run_applescript(
        _CREATE_SCRIPT,
        first,
        last or "",
        email or "",
        phone or "",
        company or "",
    )
    return {"id": pid, "success": True}


@mcp.tool(annotations=ToolAnnotations(title="Update Contact"))
def contacts_update(
    contact_id: str,
    first: str | None = None,
    last: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    company: str | None = None,
) -> dict:
    """Update fields on an existing contact."""
    sentinel = "__NO_CHANGE__"
    pid = run_applescript(
        _UPDATE_SCRIPT,
        contact_id,
        first if first is not None else sentinel,
        last if last is not None else sentinel,
        email if email is not None else sentinel,
        phone if phone is not None else sentinel,
        company if company is not None else sentinel,
    )
    return {"id": pid or contact_id, "success": True}


@mcp.tool(annotations=ToolAnnotations(title="List Contact Groups", readOnlyHint=True))
def contacts_list_groups() -> list[str]:
    """List contact groups."""
    raw = run_applescript(_GROUPS_SCRIPT)
    try:
        parsed = json.loads(raw) if raw else []
    except json.JSONDecodeError as e:
        raise RuntimeError("Failed to parse Contacts groups response") from e
    return [str(n) for n in parsed if _nn(n)]
