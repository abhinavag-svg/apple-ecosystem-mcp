from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from apple_ecosystem_mcp import server
from apple_ecosystem_mcp.tools import calendar as cal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mk_run(monkeypatch, responses):
    """Patch calendar.run_applescript with a scripted sequence of return values.

    ``responses`` may be a single string (used for every call) or a list consumed
    in call order.
    """
    if isinstance(responses, (str, list)) is False:
        raise TypeError("responses must be str or list")
    if isinstance(responses, str):
        mock = Mock(return_value=responses)
    else:
        mock = Mock(side_effect=list(responses))
    monkeypatch.setattr(cal, "run_applescript", mock)
    return mock


# ---------------------------------------------------------------------------
# Annotations
# ---------------------------------------------------------------------------


def _tools_map():
    return {t.name: t for t in server.mcp.local_provider._components.values()}


def test_readonly_tools_have_readonly_hint():
    tools = _tools_map()
    for name in (
        "calendar_list_calendars",
        "calendar_list_events",
        "calendar_get_event",
        "calendar_find_free_time",
    ):
        assert tools[name].annotations.readOnlyHint is True


def test_delete_has_destructive_hint():
    tools = _tools_map()
    assert tools["calendar_delete_event"].annotations.destructiveHint is True


# ---------------------------------------------------------------------------
# calendar_list_calendars
# ---------------------------------------------------------------------------


def test_list_calendars_returns_shape(monkeypatch):
    payload = json.dumps(
        [
            {"name": "Home", "uid": "uid-1", "account_name": "iCloud", "writable": True},
            {"name": "Holidays", "uid": "uid-2", "account_name": "Subscriptions", "writable": False},
        ]
    )
    _mk_run(monkeypatch, payload)
    result = cal.calendar_list_calendars()
    assert len(result) == 2
    for cal_rec in result:
        assert set(cal_rec.keys()) == {"name", "uid", "account_name", "writable"}
    assert result[1]["writable"] is False


def test_list_calendars_propagates_runtime_error(monkeypatch):
    def raiser(*_args, **_kwargs):
        raise RuntimeError("AppleScript failed (exit 1)")

    monkeypatch.setattr(cal, "run_applescript", raiser)
    with pytest.raises(RuntimeError):
        cal.calendar_list_calendars()


# ---------------------------------------------------------------------------
# calendar_list_events
# ---------------------------------------------------------------------------


def test_list_events_passes_args_via_argv_and_returns_records(monkeypatch):
    payload = json.dumps(
        [
            {
                "uid": "ev-1",
                "title": "Review",
                "start": "2026-04-22T10:00:00",
                "end": "2026-04-22T11:00:00",
                "location": None,
                "all_day": False,
                "calendar_uid": "uid-1",
                "calendar_name": "Work",
            }
        ]
    )
    run_mock = _mk_run(monkeypatch, payload)
    out = cal.calendar_list_events("2026-04-22T00:00:00", "2026-04-22T23:59:59", "uid-1")

    # No interpolation into AppleScript source; user data forwarded as positional argv.
    args = run_mock.call_args.args
    assert args[1] == "2026-04-22T00:00:00"
    assert args[2] == "2026-04-22T23:59:59"
    assert args[3] == "uid-1"
    assert out[0]["uid"] == "ev-1"
    assert "calendar_uid" in out[0]


def test_list_events_calendar_uid_none_sent_as_empty_string(monkeypatch):
    run_mock = _mk_run(monkeypatch, "[]")
    cal.calendar_list_events("2026-04-22", "2026-04-23")
    # None must not leak into the AppleScript arg; default is empty string.
    assert run_mock.call_args.args[3] == ""


def test_list_events_applies_default_limit(monkeypatch):
    many = [
        {
            "uid": f"ev-{i}",
            "title": f"E{i}",
            "start": "2026-04-22T09:00:00",
            "end": "2026-04-22T09:30:00",
            "location": None,
            "all_day": False,
            "calendar_uid": "u",
            "calendar_name": "c",
        }
        for i in range(120)
    ]
    _mk_run(monkeypatch, json.dumps(many))
    out = cal.calendar_list_events("2026-04-22", "2026-04-23")
    assert len(out) == cal.LIST_EVENTS_DEFAULT_LIMIT


def test_list_events_caps_at_max(monkeypatch):
    many = [
        {
            "uid": f"ev-{i}",
            "title": f"E{i}",
            "start": "2026-04-22T09:00:00",
            "end": "2026-04-22T09:30:00",
            "location": None,
            "all_day": False,
            "calendar_uid": "u",
            "calendar_name": "c",
        }
        for i in range(500)
    ]
    _mk_run(monkeypatch, json.dumps(many))
    out = cal.calendar_list_events("2026-04-22", "2026-04-23", limit=999)
    assert len(out) == cal.LIST_EVENTS_MAX_LIMIT


def test_list_events_rejects_bad_iso(monkeypatch):
    _mk_run(monkeypatch, "[]")
    with pytest.raises(RuntimeError):
        cal.calendar_list_events("not-a-date", "2026-04-22")


# ---------------------------------------------------------------------------
# calendar_get_event
# ---------------------------------------------------------------------------


def test_get_event_returns_record(monkeypatch):
    payload = json.dumps(
        {
            "uid": "ev-1",
            "title": "Review",
            "start": "2026-04-22T10:00:00",
            "end": "2026-04-22T11:00:00",
            "location": "Room 1",
            "notes": None,
            "all_day": False,
            "calendar_uid": "uid-1",
            "calendar_name": "Work",
            "invitees": [],
        }
    )
    run_mock = _mk_run(monkeypatch, payload)
    out = cal.calendar_get_event("ev-1")
    assert out["uid"] == "ev-1"
    # Event id passed as positional argv, not interpolated.
    assert run_mock.call_args.args[1] == "ev-1"


def test_get_event_not_found(monkeypatch):
    _mk_run(monkeypatch, "null")
    with pytest.raises(RuntimeError, match="Event not found"):
        cal.calendar_get_event("missing")


# ---------------------------------------------------------------------------
# calendar_create_event
# ---------------------------------------------------------------------------


def test_create_event_defaults_uid_to_empty_and_sends_argv(monkeypatch):
    # First call: calendars (for writable check). No uid supplied so this is
    # skipped by _require_writable_uid.
    run_mock = _mk_run(monkeypatch, json.dumps({"uid": "ev-new"}))
    out = cal.calendar_create_event(
        "Meeting",
        "2026-04-22T09:00:00",
        "2026-04-22T10:00:00",
    )
    # Positional args: script, calUID, title, start, end, loc, notes, inviteesCSV
    args = run_mock.call_args.args
    assert args[1] == ""  # calendar_uid=None -> ""
    assert args[2] == "Meeting"
    assert args[3] == "2026-04-22T09:00:00"
    assert args[4] == "2026-04-22T10:00:00"
    assert args[5] == ""
    assert args[6] == ""
    assert args[7] == ""
    assert out == {"uid": "ev-new", "success": True}


def test_create_event_rejects_non_writable_calendar(monkeypatch):
    calendars_payload = json.dumps(
        [{"name": "Holidays", "uid": "ro", "account_name": "Sub", "writable": False}]
    )
    # Sequence: list_calendars (for _require_writable_uid) — create must never happen.
    _mk_run(monkeypatch, [calendars_payload])
    with pytest.raises(RuntimeError, match="not writable"):
        cal.calendar_create_event(
            "X",
            "2026-04-22T09:00:00",
            "2026-04-22T10:00:00",
            calendar_uid="ro",
        )


def test_create_event_unknown_calendar(monkeypatch):
    calendars_payload = json.dumps(
        [{"name": "Work", "uid": "w", "account_name": "iCloud", "writable": True}]
    )
    _mk_run(monkeypatch, [calendars_payload])
    with pytest.raises(RuntimeError, match="not found"):
        cal.calendar_create_event(
            "X",
            "2026-04-22T09:00:00",
            "2026-04-22T10:00:00",
            calendar_uid="does-not-exist",
        )


def test_create_event_rejects_bad_iso(monkeypatch):
    _mk_run(monkeypatch, json.dumps({"uid": "x"}))
    with pytest.raises(RuntimeError):
        cal.calendar_create_event("T", "bad", "2026-04-22T10:00:00")


def test_create_event_accepts_optional_fields(monkeypatch):
    run_mock = _mk_run(monkeypatch, json.dumps({"uid": "ev-new"}))
    cal.calendar_create_event(
        "Review",
        "2026-04-22T09:00:00",
        "2026-04-22T10:00:00",
        location="HQ",
        notes="prep deck",
        invitees=["a@x.com", "b@x.com"],
    )
    args = run_mock.call_args.args
    assert args[5] == "HQ"
    assert args[6] == "prep deck"
    assert args[7] == "a@x.com,b@x.com"


# ---------------------------------------------------------------------------
# calendar_update_event
# ---------------------------------------------------------------------------


def test_update_event_uses_explicit_optional_params_not_kwargs():
    import inspect

    sig = inspect.signature(cal.calendar_update_event)
    # No **kwargs allowed per FastMCP schema generation contract.
    assert all(
        p.kind is not inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )


def test_update_event_requires_writable_calendar(monkeypatch):
    # Sequence: get_event (finds event on read-only cal), then writable check rejects.
    get_payload = json.dumps(
        {
            "uid": "ev-1",
            "title": "t",
            "start": "2026-04-22T09:00:00",
            "end": "2026-04-22T10:00:00",
            "location": None,
            "notes": None,
            "all_day": False,
            "calendar_uid": "ro",
            "calendar_name": "Holidays",
            "invitees": [],
        }
    )
    calendars_payload = json.dumps(
        [{"name": "Holidays", "uid": "ro", "account_name": "Sub", "writable": False}]
    )
    _mk_run(monkeypatch, [get_payload, calendars_payload])
    with pytest.raises(RuntimeError, match="not writable"):
        cal.calendar_update_event("ev-1", title="New")


def test_update_event_passes_only_supplied_fields(monkeypatch):
    get_payload = json.dumps(
        {
            "uid": "ev-1",
            "title": "t",
            "start": "2026-04-22T09:00:00",
            "end": "2026-04-22T10:00:00",
            "location": None,
            "notes": None,
            "all_day": False,
            "calendar_uid": "w",
            "calendar_name": "Work",
            "invitees": [],
        }
    )
    calendars_payload = json.dumps(
        [{"name": "Work", "uid": "w", "account_name": "iCloud", "writable": True}]
    )
    update_payload = json.dumps({"uid": "ev-1"})
    run_mock = _mk_run(
        monkeypatch, [get_payload, calendars_payload, update_payload]
    )
    out = cal.calendar_update_event("ev-1", title="Renamed")
    assert out == {"uid": "ev-1", "success": True}
    # Third call = the update; confirm title was passed and other fields blank.
    update_args = run_mock.call_args_list[2].args
    assert update_args[1] == "ev-1"
    assert update_args[2] == "Renamed"
    assert update_args[3] == ""  # start unchanged
    assert update_args[4] == ""  # end unchanged


# ---------------------------------------------------------------------------
# calendar_delete_event
# ---------------------------------------------------------------------------


def test_delete_event_default_confirm_false_is_preview(monkeypatch):
    preview_payload = json.dumps(
        {
            "uid": "ev-1",
            "title": "Standup",
            "start": "2026-04-22T09:00:00",
            "end": "2026-04-22T09:15:00",
            "location": None,
            "notes": None,
            "all_day": False,
            "calendar_uid": "w",
            "calendar_name": "Work",
            "invitees": [],
        }
    )
    run_mock = _mk_run(monkeypatch, [preview_payload])
    out = cal.calendar_delete_event("ev-1")
    assert out["confirmed"] is False
    assert "Standup" in out["preview"]
    # Only the get call — no delete script invoked.
    assert run_mock.call_count == 1


def test_delete_event_confirm_true_performs_delete(monkeypatch):
    run_mock = _mk_run(monkeypatch, ["ok"])
    out = cal.calendar_delete_event("ev-1", confirm=True)
    assert out == {"uid": "ev-1", "success": True}
    # Only one call — the delete script.
    assert run_mock.call_count == 1
    args = run_mock.call_args.args
    # Canonical event UID forwarded as positional argv.
    assert args[1] == "ev-1"


# ---------------------------------------------------------------------------
# calendar_find_free_time
# ---------------------------------------------------------------------------


def test_find_free_time_returns_gaps_within_working_hours(monkeypatch):
    events = [
        # 10:00–11:00 — blocks one hour inside 9–18 window.
        {
            "uid": "a",
            "title": "m1",
            "start": "2026-04-22T10:00:00",
            "end": "2026-04-22T11:00:00",
            "location": None,
            "all_day": False,
            "calendar_uid": "w",
            "calendar_name": "Work",
        },
        # 13:00–14:00.
        {
            "uid": "b",
            "title": "m2",
            "start": "2026-04-22T13:00:00",
            "end": "2026-04-22T14:00:00",
            "location": None,
            "all_day": False,
            "calendar_uid": "w",
            "calendar_name": "Work",
        },
    ]
    _mk_run(monkeypatch, json.dumps(events))
    slots = cal.calendar_find_free_time("2026-04-22", duration_minutes=30)
    # Expected slots: 09:00–10:00, 11:00–13:00, 14:00–18:00.
    assert len(slots) == 3
    assert slots[0]["start"].endswith("09:00:00")
    assert slots[0]["end"].endswith("10:00:00")
    assert slots[1]["start"].endswith("11:00:00")
    assert slots[1]["end"].endswith("13:00:00")
    assert slots[2]["start"].endswith("14:00:00")
    assert slots[2]["end"].endswith("18:00:00")


def test_find_free_time_ignores_events_outside_working_hours(monkeypatch):
    events = [
        # Event entirely before working hours.
        {
            "uid": "a",
            "title": "m1",
            "start": "2026-04-22T07:00:00",
            "end": "2026-04-22T08:00:00",
            "location": None,
            "all_day": False,
            "calendar_uid": "w",
            "calendar_name": "Work",
        },
        # Event entirely after working hours.
        {
            "uid": "b",
            "title": "m2",
            "start": "2026-04-22T19:00:00",
            "end": "2026-04-22T20:00:00",
            "location": None,
            "all_day": False,
            "calendar_uid": "w",
            "calendar_name": "Work",
        },
    ]
    _mk_run(monkeypatch, json.dumps(events))
    slots = cal.calendar_find_free_time("2026-04-22", duration_minutes=60)
    # Entire working window is free.
    assert len(slots) == 1
    assert slots[0]["start"].endswith("09:00:00")
    assert slots[0]["end"].endswith("18:00:00")
    assert slots[0]["duration_minutes"] == 9 * 60


def test_find_free_time_merges_overlapping_events(monkeypatch):
    events = [
        {
            "uid": "a",
            "title": "m1",
            "start": "2026-04-22T10:00:00",
            "end": "2026-04-22T11:30:00",
            "location": None,
            "all_day": False,
            "calendar_uid": "w",
            "calendar_name": "Work",
        },
        {
            "uid": "b",
            "title": "m2",
            "start": "2026-04-22T11:00:00",
            "end": "2026-04-22T12:00:00",
            "location": None,
            "all_day": False,
            "calendar_uid": "w",
            "calendar_name": "Work",
        },
    ]
    _mk_run(monkeypatch, json.dumps(events))
    slots = cal.calendar_find_free_time("2026-04-22", duration_minutes=30)
    # Merged busy block is 10:00–12:00, so free slots: 09:00–10:00, 12:00–18:00.
    assert len(slots) == 2
    assert slots[0]["end"].endswith("10:00:00")
    assert slots[1]["start"].endswith("12:00:00")


def test_find_free_time_respects_custom_working_hours(monkeypatch):
    _mk_run(monkeypatch, "[]")
    slots = cal.calendar_find_free_time(
        "2026-04-22", duration_minutes=30, working_hours_start=14, working_hours_end=16
    )
    assert len(slots) == 1
    assert slots[0]["start"].endswith("14:00:00")
    assert slots[0]["end"].endswith("16:00:00")


def test_find_free_time_rejects_invalid_window(monkeypatch):
    _mk_run(monkeypatch, "[]")
    with pytest.raises(RuntimeError, match="working hours"):
        cal.calendar_find_free_time(
            "2026-04-22", 30, working_hours_start=10, working_hours_end=10
        )


def test_find_free_time_rejects_nonpositive_duration(monkeypatch):
    _mk_run(monkeypatch, "[]")
    with pytest.raises(RuntimeError, match="positive"):
        cal.calendar_find_free_time("2026-04-22", 0)


def test_find_free_time_rejects_bad_iso(monkeypatch):
    _mk_run(monkeypatch, "[]")
    with pytest.raises(RuntimeError):
        cal.calendar_find_free_time("not-a-date", 30)


def test_find_free_time_skips_short_gaps(monkeypatch):
    events = [
        {
            "uid": "a",
            "title": "m1",
            "start": "2026-04-22T09:15:00",
            "end": "2026-04-22T17:45:00",
            "location": None,
            "all_day": False,
            "calendar_uid": "w",
            "calendar_name": "Work",
        }
    ]
    _mk_run(monkeypatch, json.dumps(events))
    # 15-minute gaps at either end — request 30 min, so no free slots returned.
    slots = cal.calendar_find_free_time("2026-04-22", duration_minutes=30)
    assert slots == []


def test_find_free_time_all_day_event_blocks_window(monkeypatch):
    events = [
        {
            "uid": "a",
            "title": "Holiday",
            "start": "2026-04-22T00:00:00",
            "end": "2026-04-23T00:00:00",
            "location": None,
            "all_day": True,
            "calendar_uid": "h",
            "calendar_name": "Holidays",
        }
    ]
    _mk_run(monkeypatch, json.dumps(events))
    slots = cal.calendar_find_free_time("2026-04-22", duration_minutes=30)
    assert slots == []
