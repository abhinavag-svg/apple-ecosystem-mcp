from __future__ import annotations

import gzip
import json
import sqlite3
from unittest.mock import Mock

import pytest

from apple_ecosystem_mcp import server
from apple_ecosystem_mcp.tools import notes


def _patch_run(monkeypatch, return_value):
    mock = Mock(return_value=return_value)
    monkeypatch.setattr(notes, "run_applescript", mock)
    return mock


def _varint(value: int) -> bytes:
    out = bytearray()
    while value >= 0x80:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def _field_bytes(field: int, value: bytes) -> bytes:
    return _varint((field << 3) | 2) + _varint(len(value)) + value


def _create_notes_store(path, *, title: str = "Tuscany Itinerary", text: str = "Plain itinerary text") -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            create table ZICCLOUDSYNCINGOBJECT (
                Z_PK integer primary key,
                ZMARKEDFORDELETION integer,
                ZIDENTIFIER varchar,
                ZTITLE1 varchar,
                ZMODIFICATIONDATE1 timestamp,
                ZCREATIONDATE1 timestamp,
                ZNOTEDATA integer
            );
            create table ZICNOTEDATA (
                Z_PK integer primary key,
                ZDATA blob
            );
            """
        )
        blob = gzip.compress(_field_bytes(1, text.encode("utf-8")))
        conn.execute(
            """
            insert into ZICCLOUDSYNCINGOBJECT(
                Z_PK, ZMARKEDFORDELETION, ZIDENTIFIER, ZTITLE1,
                ZMODIFICATIONDATE1, ZCREATIONDATE1, ZNOTEDATA
            ) values (162, 0, 'note-uuid', ?, 492632690, 492632000, 12)
            """,
            (title,),
        )
        conn.execute("insert into ZICNOTEDATA(Z_PK, ZDATA) values (12, ?)", (blob,))
        conn.commit()
    finally:
        conn.close()


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
    assert result[0]["next_action"]["tool"] == "notes_read"
    assert result[0]["next_action"]["arguments"] == {"note_id": "N1"}
    assert "body" not in result[0]
    assert run_mock.call_args.args[1:5] == ("iCloud", "Notes", 'quote " safe', "200")
    assert 'quote " safe' not in run_mock.call_args.args[0]


def test_notes_read_requires_target():
    with pytest.raises(RuntimeError, match="Provide title or note_id"):
        notes.notes_read()


def test_notes_read_returns_body_and_plain_text(monkeypatch):
    payload = json.dumps(
        {
            "id": "N1",
            "title": "Project",
            "body": "Hello",
            "text": "Hello",
            "body_format": "plain_text",
            "account": "iCloud",
            "folder": "Notes",
        }
    )
    _patch_run(monkeypatch, payload)
    result = notes.notes_read(note_id="N1")
    assert result["body"] == "Hello"
    assert result["text"] == "Hello"
    assert result["body_format"] == "plain_text"
    assert result["folder"] == "Notes"


def test_notes_read_uses_store_only_after_applescript_failure(monkeypatch, tmp_path):
    store_path = tmp_path / "NoteStore.sqlite"
    _create_notes_store(store_path, text="Tuscany Itinerary\n\nReadable plain text")
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_NOTES_STORE", str(store_path))
    run_mock = Mock(side_effect=RuntimeError("AppleScript timed out"))
    monkeypatch.setattr(notes, "run_applescript", run_mock)

    result = notes.notes_read(title="Tuscany Itinerary")

    assert result["id"] == "note-uuid"
    assert result["title"] == "Tuscany Itinerary"
    assert result["body"] == "Tuscany Itinerary\n\nReadable plain text"
    assert result["text"] == result["body"]
    assert result["body_format"] == "plain_text"
    run_mock.assert_called_once()


def test_notes_read_store_accepts_stable_coredata_id(monkeypatch, tmp_path):
    store_path = tmp_path / "NoteStore.sqlite"
    _create_notes_store(store_path, title="Rome", text="Rome text")
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_NOTES_STORE", str(store_path))
    # AppleScript fails, so fallback to store
    monkeypatch.setattr(notes, "run_applescript", Mock(side_effect=RuntimeError("timeout")))

    result = notes.notes_read(note_id="x-coredata://ABC/ICNote/p162")

    assert result["title"] == "Rome"
    assert result["text"] == "Rome text"


def test_notes_read_does_not_fallback_to_store_before_applescript(monkeypatch):
    store_mock = Mock(return_value={"id": "store-note"})
    monkeypatch.setattr(notes, "_read_note_from_store", store_mock)
    _patch_run(monkeypatch, json.dumps({"id": "N1", "title": "Rome", "body": "Rome", "text": "Rome"}))

    result = notes.notes_read(title="Rome")

    assert result["id"] == "N1"
    store_mock.assert_not_called()


def test_notes_read_script_does_not_use_unsupported_plaintext_property():
    read_section = notes._READ_SCRIPT
    assert "plaintext of n" not in read_section
    assert "return my _note_row_plain_text(n, folderName, accountName)" in read_section
    assert "«class text» of n" in notes._JSON_HELPERS


def test_notes_list_script_skips_content_read_for_empty_query():
    assert 'if queryText is "" then' in notes._LIST_SCRIPT
    assert "set matchesQuery to true" in notes._LIST_SCRIPT


def test_notes_normalize_truncates_large_plain_text():
    result = notes._normalize_note(
        {
            "id": "N1",
            "title": "Large",
            "text": "x" * (notes._NOTE_TEXT_MAX_CHARS + 10),
            "body_format": "plain_text",
        }
    )

    assert len(result["text"]) == notes._NOTE_TEXT_MAX_CHARS + 3
    assert result["text"].endswith("...")
    assert result["body"] == result["text"]


def test_notes_create_returns_success(monkeypatch):
    payload = json.dumps({"id": "N2", "title": "New", "body": "Body"})
    run_mock = _patch_run(monkeypatch, payload)
    result = notes.notes_create(folder="Notes", title="New", body="Body", account="iCloud")
    assert result["id"] == "N2"
    assert result["title"] == "New"
    assert result["success"] is True
    assert result["next_action"]["tool"] == "notes_read"
    assert result["next_action"]["arguments"] == {"note_id": "N2"}
    assert run_mock.call_args.args[1:5] == ("Notes", "New", "Body", "iCloud")


def test_notes_append_requires_target():
    with pytest.raises(RuntimeError, match="Provide title or note_id"):
        notes.notes_append(text="More")


def test_notes_delete_requires_confirmation(monkeypatch):
    _patch_run(monkeypatch, json.dumps({"id": "N1", "title": "Project", "body": ""}))
    result = notes.notes_delete(note_id="N1")
    assert result["preview"] == "Would delete note: Project"
    assert result["confirmed"] is False
    assert result["next_action"]["tool"] == "notes_delete"
    assert result["next_action"]["arguments"] == {"note_id": "N1", "confirm": True}


def test_notes_delete_confirmed(monkeypatch):
    _patch_run(monkeypatch, json.dumps({"id": "N1", "success": True}))
    assert notes.notes_delete(note_id="N1", confirm=True) == {"id": "N1", "success": True}
