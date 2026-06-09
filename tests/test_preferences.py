from __future__ import annotations

import json
import os

import pytest

from apple_ecosystem_mcp.preferences import (
    PreferencesDocument,
    PreferencesError,
    PreferencesReadOnlyError,
    PreferencesStore,
    SCHEMA_VERSION,
    get_preferences_path,
)


def test_get_preferences_path_uses_local_config_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_CONFIG_DIR", str(tmp_path))
    path = get_preferences_path()
    assert path == tmp_path / "preferences.json"


def test_store_loads_empty_document_when_missing(tmp_path):
    store = PreferencesStore(tmp_path / "prefs.json")
    document = store.load()
    assert isinstance(document, PreferencesDocument)
    assert document.version == SCHEMA_VERSION
    assert document.defaults == {}
    assert document.aliases == {}


def test_store_persists_default_and_alias(tmp_path):
    store = PreferencesStore(tmp_path / "prefs.json")
    target = {
        "id": "cal-1",
        "name": "Work",
        "kind": "calendar",
        "account_name": "Primary",
        "path": None,
    }

    store.set_default("calendar", target)
    store.add_alias("calendar", "Work Calendar", target)

    reloaded = store.load()
    assert reloaded.defaults["calendar"].to_dict() == target
    alias_record = reloaded.aliases["calendar"]["work calendar"]
    assert alias_record.alias == "Work Calendar"
    assert alias_record.target.to_dict() == target

    payload = json.loads((tmp_path / "prefs.json").read_text(encoding="utf-8"))
    assert payload["version"] == SCHEMA_VERSION
    assert payload["defaults"]["calendar"]["id"] == "cal-1"
    assert payload["aliases"]["calendar"]["work calendar"]["alias"] == "Work Calendar"


def test_alias_lookup_is_case_insensitive(tmp_path):
    store = PreferencesStore(tmp_path / "prefs.json")
    target = {"id": "mbx-1", "name": "Archive", "kind": "mailbox"}
    store.add_alias("mailbox", "Receipts", target)

    match = store.get_alias("mailbox", "  receipts ")
    assert match is not None
    assert match.alias == "Receipts"
    assert match.target.id == "mbx-1"


def test_remove_alias_and_default_return_flags(tmp_path):
    store = PreferencesStore(tmp_path / "prefs.json")
    target = {"id": "list-1", "name": "Personal", "kind": "reminders_list"}
    store.set_default("reminders_list", target)
    store.add_alias("reminders_list", "Home", target)

    assert store.remove_alias("reminders_list", "home") is True
    assert store.remove_alias("reminders_list", "home") is False
    assert store.clear_default("reminders_list") is True
    assert store.clear_default("reminders_list") is False


def test_load_rejects_invalid_json(tmp_path):
    path = tmp_path / "prefs.json"
    path.write_text("{not json}\n", encoding="utf-8")
    store = PreferencesStore(path)
    with pytest.raises(PreferencesError):
        store.load()


def test_store_raises_read_only_error_when_directory_is_unwritable(tmp_path):
    read_only_dir = tmp_path / "ro"
    read_only_dir.mkdir()
    os.chmod(read_only_dir, 0o555)
    try:
        store = PreferencesStore(read_only_dir / "prefs.json")
        with pytest.raises(PreferencesReadOnlyError):
            store.set_default("calendar", {"id": "cal-1", "name": "Work", "kind": "calendar"})
    finally:
        os.chmod(read_only_dir, 0o755)
