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


def _normalize_labeled_items(items) -> list[dict]:
    """Normalize legacy string lists and structured AppleScript rows."""
    normalized: list[dict] = []
    for item in items or []:
        if isinstance(item, dict):
            value = _nn(item.get("value"))
            if value:
                normalized.append({"label": _nn(item.get("label")), "value": value})
        else:
            value = _nn(item)
            if value:
                normalized.append({"label": None, "value": value})
    return normalized


def _first_labeled_value(items: list[dict]) -> str | None:
    return items[0]["value"] if items else None


_SEARCH_SCRIPT = r"""
on run argv
    set q to item 1 of argv
    set lim to (item 2 of argv) as integer
    set group_name to item 3 of argv
    if q is "" and group_name is "" then return "[]"
    set output to {}
    tell application "Contacts"
        if group_name is "" then
            set search_people to people
            if q is not "" then
                try
                    set search_people to my nativeMatches(q)
                on error
                    set search_people to people
                end try
            end if
        else
            set search_people to {}
            repeat with g in groups
                if my sameCI(name of g, group_name) then
                    set search_people to people of g
                    exit repeat
                end if
            end repeat
        end if

        set count_ to 0
        set seen_ids to {}
        repeat with p in search_people
            if count_ ≥ lim then exit repeat
            set pid to id of p
            if seen_ids does not contain pid then
                set end of seen_ids to pid
                if q is "" or my contactMatches(p, q) then
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
                    set email_list to my labeledEmails(p)
                    set phone_list to my labeledPhones(p)
                    set group_list to my groupNamesForPerson(p)
                    set end of output to {pid, pfirst, plast, my firstValue(email_list), my firstValue(phone_list), porg, email_list, phone_list, group_list}
                    set count_ to count_ + 1
                end if
            end if
        end repeat
    end tell
    return my jsonify(output)
end run

on nativeMatches(q)
    tell application "Contacts"
        set matches to {}
        set matches to matches & (people whose first name contains q)
        set matches to matches & (people whose last name contains q)
        set matches to matches & (people whose organization contains q)
        set matches to matches & (people whose value of emails contains q)
        set matches to matches & (people whose value of phones contains q)
        return matches
    end tell
end nativeMatches

on contactMatches(p, q)
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
    if my containsCI(pfirst, q) or my containsCI(plast, q) or my containsCI((pfirst & " " & plast), q) or my containsCI(porg, q) then return true
    try
        repeat with e in emails of p
            if my containsCI(value of e, q) then return true
        end repeat
    end try
    try
        repeat with ph in phones of p
            if my containsCI(value of ph, q) then return true
        end repeat
    end try
    return false
end contactMatches

on containsCI(hay, needle)
    try
        ignoring case
            return ((hay as string) contains (needle as string))
        end ignoring
    on error
        return false
    end try
end containsCI

on sameCI(left_, right_)
    try
        ignoring case
            return ((left_ as string) is (right_ as string))
        end ignoring
    on error
        return false
    end try
end sameCI

on firstValue(labeled_items)
    try
        if (count of labeled_items) > 0 then return item 2 of item 1 of labeled_items
    end try
    return ""
end firstValue

on labeledEmails(p)
    set email_list to {}
    try
        repeat with e in emails of p
            set elabel to ""
            try
                set elabel to label of e as string
            end try
            set evalue to ""
            try
                set evalue to value of e as string
            end try
            set end of email_list to {elabel, evalue}
        end repeat
    end try
    return email_list
end labeledEmails

on labeledPhones(p)
    set phone_list to {}
    try
        repeat with ph in phones of p
            set plabel to ""
            try
                set plabel to label of ph as string
            end try
            set pvalue to ""
            try
                set pvalue to value of ph as string
            end try
            set end of phone_list to {plabel, pvalue}
        end repeat
    end try
    return phone_list
end labeledPhones

on groupNamesForPerson(p)
    set group_list to {}
    tell application "Contacts"
        try
            repeat with g in groups
                try
                    if (people of g) contains p then set end of group_list to name of g
                end try
            end repeat
        end try
    end tell
    return group_list
end groupNamesForPerson

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
            "\"company\":" & my jstr(item 6 of r) & "," & ¬
            "\"emails\":" & my jlabeled(item 7 of r) & "," & ¬
            "\"phones\":" & my jlabeled(item 8 of r) & "," & ¬
            "\"groups\":" & my jarr(item 9 of r) & "}"
    end repeat
    set out to out & "]"
    return out
end jsonify

on jlabeled(xs)
    set out to "["
    set first_item to true
    repeat with x in xs
        if first_item then
            set first_item to false
        else
            set out to out & ","
        end if
        set out to out & "{" & "\"label\":" & my jstr(item 1 of x) & "," & "\"value\":" & my jstr(item 2 of x) & "}"
    end repeat
    set out to out & "]"
    return out
end jlabeled

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
        set email_list to my labeledEmails(p)
        set phone_list to my labeledPhones(p)
        set group_list to my groupNamesForPerson(p)
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
        "\"emails\":" & my jlabeled(email_list) & "," & ¬
        "\"phones\":" & my jlabeled(phone_list) & "," & ¬
        "\"groups\":" & my jarr(group_list) & "," & ¬
        "\"addresses\":" & my jarr(addr_list) & "}"
    return out
end run

on labeledEmails(p)
    set email_list to {}
    try
        repeat with e in emails of p
            set elabel to ""
            try
                set elabel to label of e as string
            end try
            set evalue to ""
            try
                set evalue to value of e as string
            end try
            set end of email_list to {elabel, evalue}
        end repeat
    end try
    return email_list
end labeledEmails

on labeledPhones(p)
    set phone_list to {}
    try
        repeat with ph in phones of p
            set plabel to ""
            try
                set plabel to label of ph as string
            end try
            set pvalue to ""
            try
                set pvalue to value of ph as string
            end try
            set end of phone_list to {plabel, pvalue}
        end repeat
    end try
    return phone_list
end labeledPhones

on groupNamesForPerson(p)
    set group_list to {}
    tell application "Contacts"
        try
            repeat with g in groups
                try
                    if (people of g) contains p then set end of group_list to name of g
                end try
            end repeat
        end try
    end tell
    return group_list
end groupNamesForPerson

on jlabeled(xs)
    set out to "["
    set first_item to true
    repeat with x in xs
        if first_item then
            set first_item to false
        else
            set out to out & ","
        end if
        set out to out & "{" & "\"label\":" & my jstr(item 1 of x) & "," & "\"value\":" & my jstr(item 2 of x) & "}"
    end repeat
    set out to out & "]"
    return out
end jlabeled

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
def contacts_search(query: str, limit: int = _SEARCH_LIMIT_DEFAULT, group: str | None = None) -> list[dict]:
    """Search contacts by name, email, phone, or company."""
    capped = max(1, min(int(limit), _SEARCH_LIMIT_MAX))
    raw = run_applescript(_SEARCH_SCRIPT, query, str(capped), group or "")
    try:
        parsed = json.loads(raw) if raw else []
    except json.JSONDecodeError as e:
        raise RuntimeError("Failed to parse Contacts search response") from e
    results: list[dict] = []
    for row in parsed[:capped]:
        emails = _normalize_labeled_items(row.get("emails"))
        phones = _normalize_labeled_items(row.get("phones"))
        email = _nn(row.get("email")) or _first_labeled_value(emails)
        phone = _nn(row.get("phone")) or _first_labeled_value(phones)
        results.append(
            {
                "id": row.get("id"),
                "first": _nn(row.get("first")),
                "last": _nn(row.get("last")),
                "email": email,
                "phone": phone,
                "company": _nn(row.get("company")),
                "emails": emails,
                "phones": phones,
                "groups": [g for g in (row.get("groups") or []) if _nn(g)],
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

    emails = _normalize_labeled_items(data.get("emails"))
    phones = _normalize_labeled_items(data.get("phones"))
    addresses = [a for a in (data.get("addresses") or []) if _nn(a)]
    groups = [g for g in (data.get("groups") or []) if _nn(g)]

    result = {
        "id": data.get("id") or contact_id,
        "first": _nn(data.get("first")),
        "last": _nn(data.get("last")),
        "company": _nn(data.get("company")),
        "email": _first_labeled_value(emails),
        "phone": _first_labeled_value(phones),
        "emails": emails,
        "phones": phones,
        "groups": groups,
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
