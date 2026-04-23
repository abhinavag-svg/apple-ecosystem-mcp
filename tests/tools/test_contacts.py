from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from apple_ecosystem_mcp.tools import contacts


def _patch_run(monkeypatch, return_value):
    mock = Mock(return_value=return_value)
    monkeypatch.setattr(contacts, "run_applescript", mock)
    return mock


def test_contacts_search_returns_canonical_shape(monkeypatch):
    payload = json.dumps(
        [
            {
                "id": "ABC-123",
                "first": "Ada",
                "last": "Lovelace",
                "email": "ada@example.com",
                "phone": "+1-555-0100",
                "company": "Analytical",
            }
        ]
    )
    run_mock = _patch_run(monkeypatch, payload)
    results = contacts.contacts_search("Ada")
    assert results == [
        {
            "id": "ABC-123",
            "first": "Ada",
            "last": "Lovelace",
            "email": "ada@example.com",
            "phone": "+1-555-0100",
            "company": "Analytical",
        }
    ]
    # argv[0] is the script, args[1] is query, args[2] is limit (as string)
    call = run_mock.call_args
    assert call.args[1] == "Ada"
    assert call.args[2] == "10"


def test_contacts_search_default_limit_is_10(monkeypatch):
    run_mock = _patch_run(monkeypatch, "[]")
    contacts.contacts_search("x")
    assert run_mock.call_args.args[2] == "10"


def test_contacts_search_caps_at_max_50(monkeypatch):
    run_mock = _patch_run(monkeypatch, "[]")
    contacts.contacts_search("x", limit=500)
    assert run_mock.call_args.args[2] == "50"


def test_contacts_search_enforces_slice(monkeypatch):
    # Simulate an AppleScript returning 100 rows (shouldn't happen in practice
    # since the script respects the limit argument, but the Python side must
    # still slice defensively).
    rows = [
        {"id": f"id-{i}", "first": f"F{i}", "last": None, "email": None, "phone": None, "company": None}
        for i in range(100)
    ]
    _patch_run(monkeypatch, json.dumps(rows))
    out = contacts.contacts_search("x", limit=5)
    assert len(out) == 5


def test_contacts_search_missing_value_normalized(monkeypatch):
    payload = json.dumps(
        [
            {
                "id": "X",
                "first": "",
                "last": "missing value",
                "email": None,
                "phone": "",
                "company": None,
            }
        ]
    )
    _patch_run(monkeypatch, payload)
    out = contacts.contacts_search("x")
    assert out[0]["first"] is None
    assert out[0]["last"] is None
    assert out[0]["email"] is None
    assert out[0]["phone"] is None
    assert out[0]["company"] is None


def test_contacts_search_uses_argv_not_interpolation(monkeypatch):
    run_mock = _patch_run(monkeypatch, "[]")
    # A malicious-looking query must still be passed as an argv argument,
    # never interpolated into the script body.
    nasty = 'hack"; do shell script "rm -rf /"'
    contacts.contacts_search(nasty)
    script_src = run_mock.call_args.args[0]
    assert nasty not in script_src
    assert run_mock.call_args.args[1] == nasty


def test_contacts_get_returns_canonical_record(monkeypatch):
    payload = json.dumps(
        {
            "id": "UUID-1",
            "first": "Ada",
            "last": "Lovelace",
            "company": "Analytical",
            "notes": "Hello",
            "birthday": "1815-12-10T00:00:00",
            "emails": ["a@example.com", "b@example.com"],
            "phones": ["+1-555-0100"],
            "addresses": ["10 Downing St, London"],
        }
    )
    run_mock = _patch_run(monkeypatch, payload)
    record = contacts.contacts_get("UUID-1")
    assert record["id"] == "UUID-1"
    assert record["first"] == "Ada"
    assert record["last"] == "Lovelace"
    assert record["emails"] == ["a@example.com", "b@example.com"]
    assert record["phones"] == ["+1-555-0100"]
    assert record["addresses"] == ["10 Downing St, London"]
    assert record["birthday"] == "1815-12-10T00:00:00"
    assert record["notes"] == "Hello"
    # contact_id routed through argv
    assert run_mock.call_args.args[1] == "UUID-1"


def test_contacts_get_truncates_long_notes(monkeypatch):
    long_notes = "x" * 3000
    payload = json.dumps(
        {
            "id": "UUID-2",
            "first": "A",
            "last": None,
            "company": None,
            "notes": long_notes,
            "birthday": None,
            "emails": [],
            "phones": [],
            "addresses": [],
        }
    )
    _patch_run(monkeypatch, payload)
    record = contacts.contacts_get("UUID-2")
    # First 2000 chars preserved; truncation marker appended
    assert record["notes"].startswith("x" * 2000)
    assert "[truncated — 1000 chars omitted]" in record["notes"]
    assert record["notes_truncated"] is True


def test_contacts_get_normalizes_missing_fields(monkeypatch):
    payload = json.dumps(
        {
            "id": "UUID-3",
            "first": "missing value",
            "last": "",
            "company": None,
            "notes": "",
            "birthday": "missing value",
            "emails": ["", "missing value"],
            "phones": [],
            "addresses": ["", ""],
        }
    )
    _patch_run(monkeypatch, payload)
    record = contacts.contacts_get("UUID-3")
    assert record["first"] is None
    assert record["last"] is None
    assert record["company"] is None
    assert record["birthday"] is None
    assert record["emails"] == []
    assert record["phones"] == []
    assert record["addresses"] == []


def test_contacts_create_returns_id_and_success(monkeypatch):
    run_mock = _patch_run(monkeypatch, "NEW-UUID")
    out = contacts.contacts_create(
        first="Grace",
        last="Hopper",
        email="grace@example.com",
        phone="+1-555-0200",
        company="Navy",
    )
    assert out == {"id": "NEW-UUID", "success": True}
    call = run_mock.call_args
    assert call.args[1] == "Grace"
    assert call.args[2] == "Hopper"
    assert call.args[3] == "grace@example.com"
    assert call.args[4] == "+1-555-0200"
    assert call.args[5] == "Navy"


def test_contacts_create_optional_fields_become_empty_strings(monkeypatch):
    run_mock = _patch_run(monkeypatch, "NEW-UUID")
    contacts.contacts_create(first="Solo")
    call = run_mock.call_args
    assert call.args[1] == "Solo"
    assert call.args[2] == ""
    assert call.args[3] == ""
    assert call.args[4] == ""
    assert call.args[5] == ""


def test_contacts_update_sends_sentinel_for_unchanged_fields(monkeypatch):
    run_mock = _patch_run(monkeypatch, "UUID-4")
    out = contacts.contacts_update("UUID-4", first="NewFirst")
    assert out == {"id": "UUID-4", "success": True}
    call = run_mock.call_args
    assert call.args[1] == "UUID-4"
    assert call.args[2] == "NewFirst"
    assert call.args[3] == "__NO_CHANGE__"
    assert call.args[4] == "__NO_CHANGE__"
    assert call.args[5] == "__NO_CHANGE__"
    assert call.args[6] == "__NO_CHANGE__"


def test_contacts_update_explicit_optional_params_not_kwargs():
    import inspect

    sig = inspect.signature(contacts.contacts_update)
    param_kinds = {p.kind for p in sig.parameters.values()}
    assert inspect.Parameter.VAR_KEYWORD not in param_kinds
    assert inspect.Parameter.VAR_POSITIONAL not in param_kinds
    # All update-able fields are explicit
    assert set(sig.parameters) == {"contact_id", "first", "last", "email", "phone", "company"}


def test_contacts_list_groups_returns_names(monkeypatch):
    _patch_run(monkeypatch, json.dumps(["Friends", "Work", "Family"]))
    out = contacts.contacts_list_groups()
    assert out == ["Friends", "Work", "Family"]


def test_contacts_list_groups_filters_empty_and_missing(monkeypatch):
    _patch_run(monkeypatch, json.dumps(["Friends", "", "missing value", "Work"]))
    out = contacts.contacts_list_groups()
    assert out == ["Friends", "Work"]


def test_contacts_permission_failure_surfaces_as_runtime_error(monkeypatch):
    def raise_runtime(*args, **kwargs):
        raise RuntimeError("AppleScript failed (exit 1)")

    monkeypatch.setattr(contacts, "run_applescript", raise_runtime)
    with pytest.raises(RuntimeError) as e:
        contacts.contacts_search("x")
    assert "AppleScript failed" in str(e.value)


def test_contacts_search_invalid_json_raises(monkeypatch):
    _patch_run(monkeypatch, "not-json{")
    with pytest.raises(RuntimeError) as e:
        contacts.contacts_search("x")
    assert "parse" in str(e.value).lower()
