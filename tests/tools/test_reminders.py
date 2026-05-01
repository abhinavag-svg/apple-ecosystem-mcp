from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from apple_ecosystem_mcp.tools import reminders


def _patch_run(monkeypatch, return_value):
    mock = Mock(return_value=return_value)
    monkeypatch.setattr(reminders, "run_applescript", mock)
    return mock


def test_reminders_lists_returns_user_names(monkeypatch):
    _patch_run(monkeypatch, json.dumps(["Reminders", "Groceries", "Work"]))
    out = reminders.reminders_lists()
    assert out == ["Reminders", "Groceries", "Work"]


def test_reminders_lists_can_return_stable_ids(monkeypatch):
    _patch_run(
        monkeypatch,
        json.dumps(
            [
                {"id": "LIST-1", "name": "Reminders"},
                {"id": "LIST-2", "name": "Groceries"},
            ]
        ),
    )
    out = reminders.reminders_lists(include_metadata=True)
    assert out == [
        {"id": "LIST-1", "name": "Reminders"},
        {"id": "LIST-2", "name": "Groceries"},
    ]


def test_reminders_lists_preserves_name_compatibility_for_metadata_payload(monkeypatch):
    _patch_run(monkeypatch, json.dumps([{"id": "LIST-1", "name": "Reminders"}]))
    out = reminders.reminders_lists()
    assert out == ["Reminders"]


def test_reminders_lists_filters_missing_and_empty(monkeypatch):
    _patch_run(
        monkeypatch,
        json.dumps(
            [
                {"id": "LIST-1", "name": "Reminders"},
                {"id": "EMPTY", "name": ""},
                {"id": "MISSING", "name": "missing value"},
            ]
        ),
    )
    out = reminders.reminders_lists()
    assert out == ["Reminders"]


def test_reminders_list_filters_by_list_name(monkeypatch):
    run_mock = _patch_run(monkeypatch, "[]")
    reminders.reminders_list(list_name="Groceries")
    assert run_mock.call_args.args[1] == ""
    assert run_mock.call_args.args[2] == "Groceries"
    # completed=False by default
    assert run_mock.call_args.args[3] == "false"


def test_reminders_list_filters_by_stable_list_id(monkeypatch):
    run_mock = _patch_run(monkeypatch, "[]")
    reminders.reminders_list(reminders_list_id="LIST-2", list_name="Duplicate Name")
    assert run_mock.call_args.args[1] == "LIST-2"
    assert run_mock.call_args.args[2] == "Duplicate Name"
    assert run_mock.call_args.args[3] == "false"


def test_reminders_list_default_list_name_is_empty_string(monkeypatch):
    # list_name=None means "all reminders"; bridge is called with "" arg.
    run_mock = _patch_run(monkeypatch, "[]")
    reminders.reminders_list()
    assert run_mock.call_args.args[1] == ""
    assert run_mock.call_args.args[2] == ""


def test_reminders_list_filters_by_completed_flag(monkeypatch):
    run_mock = _patch_run(monkeypatch, "[]")
    reminders.reminders_list(completed=True)
    assert run_mock.call_args.args[3] == "true"


def test_reminders_list_returns_canonical_shape(monkeypatch):
    payload = json.dumps(
        [
            {
                "id": "R-UUID-1",
                "title": "Buy milk",
                "notes": "2%",
                "due": "2026-04-23T09:00:00",
                "priority": 5,
                "list_name": "Groceries",
                "list_id": "LIST-2",
                "recurrence": "weekly",
                "tags": ["errands", "home"],
                "completed": False,
            }
        ]
    )
    _patch_run(monkeypatch, payload)
    out = reminders.reminders_list(list_name="Groceries")
    assert out == [
        {
            "id": "R-UUID-1",
            "title": "Buy milk",
            "notes": "2%",
            "due": "2026-04-23T09:00:00",
            "priority": 5,
            "list_name": "Groceries",
            "list_id": "LIST-2",
            "recurrence": "weekly",
            "tags": ["errands", "home"],
            "completed": False,
        }
    ]


def test_reminders_list_normalizes_missing_values(monkeypatch):
    payload = json.dumps(
        [
            {
                "id": "R-UUID-2",
                "title": "No notes",
                "notes": "",
                "due": "missing value",
                "priority": 0,
                "list_name": "Reminders",
                "list_id": "",
                "recurrence": "",
                "tags": ["", "missing value"],
                "completed": False,
            }
        ]
    )
    _patch_run(monkeypatch, payload)
    out = reminders.reminders_list()
    assert out[0]["notes"] is None
    assert out[0]["due"] is None
    assert out[0]["list_id"] is None
    assert out[0]["recurrence"] is None
    assert out[0]["tags"] == []


def test_reminders_create_accepts_due_notes_priority(monkeypatch):
    run_mock = _patch_run(monkeypatch, "R-UUID-NEW")
    result = reminders.reminders_create(
        title="Follow up",
        list_name="Work",
        due="2026-04-25T14:30:00",
        notes="Check the proposal",
        priority=5,
    )
    assert result == {"id": "R-UUID-NEW", "success": True}
    call = run_mock.call_args
    assert call.args[1] == "Follow up"
    assert call.args[2] == ""
    assert call.args[3] == "Work"
    assert call.args[4] == "2026-04-25T14:30:00"
    assert call.args[5] == "Check the proposal"
    assert call.args[6] == "5"


def test_reminders_create_targets_stable_list_id(monkeypatch):
    run_mock = _patch_run(monkeypatch, "R-UUID-NEW")
    result = reminders.reminders_create(
        title="Follow up",
        reminders_list_id="LIST-2",
        list_name="Duplicate Name",
    )
    assert result == {"id": "R-UUID-NEW", "success": True}
    call = run_mock.call_args
    assert call.args[1] == "Follow up"
    assert call.args[2] == "LIST-2"
    assert call.args[3] == "Duplicate Name"


def test_reminders_create_defaults(monkeypatch):
    run_mock = _patch_run(monkeypatch, "R-UUID-NEW")
    reminders.reminders_create(title="Simple")
    call = run_mock.call_args
    assert call.args[1] == "Simple"
    assert call.args[2] == ""  # reminders_list_id=None delegates to AppleScript
    assert call.args[3] == ""  # list_name=None delegates to AppleScript
    assert call.args[4] == ""  # no due date
    assert call.args[5] == ""  # no notes
    assert call.args[6] == "0"  # priority=0


def test_reminders_create_rejects_invalid_iso(monkeypatch):
    _patch_run(monkeypatch, "R-UUID-NEW")
    with pytest.raises(RuntimeError) as e:
        reminders.reminders_create(title="bad", due="not-a-date")
    assert "ISO 8601" in str(e.value)


def test_reminders_create_accepts_date_only_iso(monkeypatch):
    run_mock = _patch_run(monkeypatch, "R-UUID-NEW")
    reminders.reminders_create(title="ok", due="2026-04-25")
    # Date-only input is normalized to full timestamp (midnight local time)
    assert run_mock.call_args.args[4] == "2026-04-25T00:00:00"


def test_reminders_create_uses_argv_not_interpolation(monkeypatch):
    run_mock = _patch_run(monkeypatch, "R-UUID-NEW")
    nasty = 'hack"; do shell script "evil"'
    reminders.reminders_create(title=nasty, list_name=nasty, notes=nasty)
    call = run_mock.call_args
    script_src = call.args[0]
    assert nasty not in script_src
    assert call.args[1] == nasty
    assert call.args[3] == nasty
    assert call.args[5] == nasty


def test_reminders_complete_uses_canonical_id(monkeypatch):
    run_mock = _patch_run(monkeypatch, "R-UUID-3")
    out = reminders.reminders_complete("R-UUID-3")
    assert out == {"id": "R-UUID-3", "success": True}
    assert run_mock.call_args.args[1] == "R-UUID-3"


def test_reminders_delete_uses_canonical_id(monkeypatch):
    run_mock = _patch_run(monkeypatch, "R-UUID-4")
    out = reminders.reminders_delete("R-UUID-4")
    assert out == {"id": "R-UUID-4", "success": True}
    assert run_mock.call_args.args[1] == "R-UUID-4"


def test_reminders_list_explicit_params_not_kwargs():
    import inspect

    for fn in (
        reminders.reminders_lists,
        reminders.reminders_list,
        reminders.reminders_create,
        reminders.reminders_complete,
        reminders.reminders_delete,
    ):
        sig = inspect.signature(fn)
        kinds = {p.kind for p in sig.parameters.values()}
        assert inspect.Parameter.VAR_KEYWORD not in kinds
        assert inspect.Parameter.VAR_POSITIONAL not in kinds


def test_reminders_permission_failure_surfaces_as_runtime_error(monkeypatch):
    def raise_runtime(*args, **kwargs):
        raise RuntimeError("Execution error: Not authorized to send Apple events. (-1743)")

    monkeypatch.setattr(reminders, "run_applescript", raise_runtime)
    with pytest.raises(RuntimeError) as e:
        reminders.reminders_lists()
    assert "Reminders automation is not authorized" in str(e.value)


def test_reminders_permission_sentinel_surfaces_standard_error(monkeypatch):
    _patch_run(monkeypatch, reminders._PERMISSION_DENIED_SENTINEL)
    with pytest.raises(RuntimeError) as e:
        reminders.reminders_list()
    assert "Reminders automation is not authorized" in str(e.value)


def test_reminders_list_invalid_json_raises(monkeypatch):
    _patch_run(monkeypatch, "not-json{")
    with pytest.raises(RuntimeError) as e:
        reminders.reminders_list()
    assert "parse" in str(e.value).lower()
