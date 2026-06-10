from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from apple_ecosystem_mcp import server
from apple_ecosystem_mcp.tools import notes


def _patch_run(monkeypatch, return_value):
    mock = Mock(return_value=return_value)
    monkeypatch.setattr(notes, "run_applescript", mock)
    return mock


def _tools_map():
    return {t.name: t for t in server.mcp.local_provider._components.values()}


def test_notes_tools_have_annotations():
    tools = _tools_map()
    assert tools["notes_accounts"].annotations.readOnlyHint is True
    assert tools["notes_folders"].annotations.readOnlyHint is True
    assert tools["notes_list"].annotations.readOnlyHint is True
    assert tools["notes_search"].annotations.readOnlyHint is True
    assert tools["notes_read"].annotations.readOnlyHint is True
    assert tools["notes_delete"].annotations.destructiveHint is True


def test_notes_accounts_returns_structured_rows(monkeypatch):
    _patch_run(monkeypatch, json.dumps([{"id": "A1", "name": "iCloud", "kind": "notes_account"}]))
    assert notes.notes_accounts() == [{"id": "A1", "name": "iCloud", "kind": "notes_account"}]


def test_notes_folders_scopes_to_account(monkeypatch):
    run_mock = _patch_run(monkeypatch, json.dumps([{"id": "F1", "name": "Ideas", "account": "iCloud"}]))
    assert notes.notes_folders(account="iCloud")[0]["name"] == "Ideas"
    assert run_mock.call_args.args[1] == "iCloud"


def test_notes_search_uses_argv_and_returns_summaries(monkeypatch):
    payload = json.dumps(
        [
            {
                "id": "N1",
                "title": "Project",
                "body": "<p>Hello<br>world</p>",
                "account": "iCloud",
                "folder": "Notes",
                "created": "2026-06-10T10:00:00",
                "modified": "2026-06-10T11:00:00",
            }
        ]
    )
    run_mock = _patch_run(monkeypatch, payload)
    result = notes.notes_search('quote " safe', account="iCloud", folder="Notes", limit=500)
    assert result[0]["id"] == "N1"
    assert result[0]["preview"] == "Hello\nworld"
    assert "body" not in result[0]
    assert run_mock.call_args.args[1:5] == ("iCloud", "Notes", 'quote " safe', "200")
    assert 'quote " safe' not in run_mock.call_args.args[0]


def test_notes_read_requires_target():
    with pytest.raises(RuntimeError, match="Provide title or note_id"):
        notes.notes_read()


def test_notes_read_returns_body_and_plain_text(monkeypatch):
    payload = json.dumps({"id": "N1", "title": "Project", "body": "<p>Hello</p>", "account": "iCloud"})
    _patch_run(monkeypatch, payload)
    result = notes.notes_read(note_id="N1")
    assert result["body"] == "<p>Hello</p>"
    assert result["text"] == "Hello"


def test_notes_create_returns_success(monkeypatch):
    payload = json.dumps({"id": "N2", "title": "New", "body": "Body"})
    run_mock = _patch_run(monkeypatch, payload)
    result = notes.notes_create(folder="Notes", title="New", body="Body", account="iCloud")
    assert result == {"id": "N2", "title": "New", "success": True}
    assert run_mock.call_args.args[1:5] == ("Notes", "New", "Body", "iCloud")


def test_notes_append_requires_target():
    with pytest.raises(RuntimeError, match="Provide title or note_id"):
        notes.notes_append(text="More")


def test_notes_delete_requires_confirmation(monkeypatch):
    _patch_run(monkeypatch, json.dumps({"id": "N1", "title": "Project", "body": ""}))
    result = notes.notes_delete(note_id="N1")
    assert result == {"preview": "Would delete note: Project", "confirmed": False}


def test_notes_delete_confirmed(monkeypatch):
    _patch_run(monkeypatch, json.dumps({"id": "N1", "success": True}))
    assert notes.notes_delete(note_id="N1", confirm=True) == {"id": "N1", "success": True}
