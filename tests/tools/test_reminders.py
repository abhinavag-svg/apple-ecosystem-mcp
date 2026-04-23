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


def test_reminders_lists_filters_missing_and_empty(monkeypatch):
    _patch_run(monkeypatch, json.dumps(["Reminders", "", "missing value"]))
    out = reminders.reminders_lists()
    assert out == ["Reminders"]


def test_reminders_list_filters_by_list_name(monkeypatch):
    run_mock = _patch_run(monkeypatch, "[]")
    reminders.reminders_list(list_name="Groceries")
    assert run_mock.call_args.args[1] == "Groceries"
    # completed=False by default
    assert run_mock.call_args.args[2] == "false"


def test_reminders_list_default_list_name_is_empty_string(monkeypatch):
    # list_name=None means "all reminders"; bridge is called with "" arg.
    run_mock = _patch_run(monkeypatch, "[]")
    reminders.reminders_list()
    assert run_mock.call_args.args[1] == ""


def test_reminders_list_filters_by_completed_flag(monkeypatch):
    run_mock = _patch_run(monkeypatch, "[]")
    reminders.reminders_list(completed=True)
    assert run_mock.call_args.args[2] == "true"


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
                "completed": False,
            }
        ]
    )
    _patch_run(monkeypatch, payload)
    out = reminders.reminders_list()
    assert out[0]["notes"] is None
    assert out[0]["due"] is None


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
    assert call.args[2] == "Work"
    assert call.args[3] == "2026-04-25T14:30:00"
    assert call.args[4] == "Check the proposal"
    assert call.args[5] == "5"


def test_reminders_create_defaults(monkeypatch):
    run_mock = _patch_run(monkeypatch, "R-UUID-NEW")
    reminders.reminders_create(title="Simple")
    call = run_mock.call_args
    assert call.args[1] == "Simple"
    assert call.args[2] == "Reminders"
    assert call.args[3] == ""
    assert call.args[4] == ""
    assert call.args[5] == "0"


def test_reminders_create_rejects_invalid_iso(monkeypatch):
    _patch_run(monkeypatch, "R-UUID-NEW")
    with pytest.raises(RuntimeError) as e:
        reminders.reminders_create(title="bad", due="not-a-date")
    assert "ISO 8601" in str(e.value)


def test_reminders_create_accepts_date_only_iso(monkeypatch):
    run_mock = _patch_run(monkeypatch, "R-UUID-NEW")
    reminders.reminders_create(title="ok", due="2026-04-25")
    assert run_mock.call_args.args[3] == "2026-04-25"


def test_reminders_create_uses_argv_not_interpolation(monkeypatch):
    run_mock = _patch_run(monkeypatch, "R-UUID-NEW")
    nasty = 'hack"; do shell script "evil"'
    reminders.reminders_create(title=nasty, list_name=nasty, notes=nasty)
    call = run_mock.call_args
    script_src = call.args[0]
    assert nasty not in script_src
    assert call.args[1] == nasty
    assert call.args[2] == nasty
    assert call.args[4] == nasty


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
        raise RuntimeError("AppleScript failed (exit 1)")

    monkeypatch.setattr(reminders, "run_applescript", raise_runtime)
    with pytest.raises(RuntimeError) as e:
        reminders.reminders_lists()
    assert "AppleScript failed" in str(e.value)


def test_reminders_list_invalid_json_raises(monkeypatch):
    _patch_run(monkeypatch, "not-json{")
    with pytest.raises(RuntimeError) as e:
        reminders.reminders_list()
    assert "parse" in str(e.value).lower()
