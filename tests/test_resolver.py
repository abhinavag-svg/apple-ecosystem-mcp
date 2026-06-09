from __future__ import annotations

import pytest

from apple_ecosystem_mcp.preferences import PreferencesStore
from apple_ecosystem_mcp.resolver import (
    AmbiguousTargetError,
    ReadOnlyTargetError,
    TargetNotFoundError,
    resolve_target,
)


@pytest.fixture
def inventory() -> list[dict[str, object]]:
    return [
        {
            "id": "cal-1",
            "name": "Work",
            "kind": "calendar",
            "account_name": "Primary",
            "writable": True,
        },
        {
            "id": "cal-2",
            "name": "Work",
            "kind": "calendar",
            "account_name": "Shared",
            "writable": False,
        },
        {
            "id": "cal-3",
            "name": "Personal",
            "kind": "calendar",
            "account_name": "Primary",
            "writable": True,
            "path": "/Calendars/Personal",
        },
    ]


def test_resolve_target_uses_default_when_query_missing(tmp_path, inventory):
    store = PreferencesStore(tmp_path / "prefs.json")
    store.set_default(
        "calendar",
        {"id": "cal-3", "name": "Personal", "kind": "calendar", "account_name": "Primary"},
    )

    resolved = resolve_target(None, inventory, scope="calendar", preferences=store)
    assert resolved.source == "default"
    assert resolved.item["id"] == "cal-3"


def test_resolve_target_uses_alias(tmp_path, inventory):
    store = PreferencesStore(tmp_path / "prefs.json")
    store.add_alias(
        "calendar",
        "Home",
        {"id": "cal-3", "name": "Personal", "kind": "calendar", "account_name": "Primary"},
    )

    resolved = resolve_target("home", inventory, scope="calendar", preferences=store)
    assert resolved.source == "alias"
    assert resolved.item["name"] == "Personal"


def test_resolve_target_prefers_exact_id(inventory):
    resolved = resolve_target("cal-2", inventory, scope="calendar")
    assert resolved.source == "id"
    assert resolved.item["account_name"] == "Shared"


def test_resolve_target_reports_ambiguous_name(inventory):
    with pytest.raises(AmbiguousTargetError) as excinfo:
        resolve_target("Work", inventory, scope="calendar")

    data = excinfo.value.to_dict()
    assert data["error"] == "target_ambiguous"
    assert len(data["candidates"]) == 2


def test_resolve_target_reports_read_only_target(inventory):
    with pytest.raises(ReadOnlyTargetError) as excinfo:
        resolve_target("Shared/Work", inventory, scope="calendar", require_writable=True)

    data = excinfo.value.to_dict()
    assert data["error"] == "target_read_only"
    assert data["target"]["id"] == "cal-2"


def test_resolve_target_reports_stale_default(tmp_path, inventory):
    store = PreferencesStore(tmp_path / "prefs.json")
    store.set_default(
        "calendar",
        {"id": "missing", "name": "Ghost", "kind": "calendar", "account_name": "Primary"},
    )

    with pytest.raises(TargetNotFoundError) as excinfo:
        resolve_target(None, inventory, scope="calendar", preferences=store)

    data = excinfo.value.to_dict()
    assert data["error"] == "target_not_found"
    assert "no longer available" in data["message"]


def test_resolve_target_uses_unique_partial_match(inventory):
    resolved = resolve_target("person", inventory, scope="calendar")
    assert resolved.source == "partial"
    assert resolved.item["id"] == "cal-3"
