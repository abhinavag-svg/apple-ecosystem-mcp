from __future__ import annotations

from unittest.mock import Mock

from apple_ecosystem_mcp.tools import preferences as prefs


def test_inventory_combines_existing_discovery_functions(monkeypatch):
    monkeypatch.setattr(
        prefs.calendar_tools,
        "calendar_list_calendars",
        Mock(return_value=[{"id": "cal-1", "name": "Work", "kind": "calendar", "writable": True}]),
    )
    monkeypatch.setattr(
        prefs.mail_tools,
        "mail_list_mailboxes",
        Mock(return_value=[{"id": "mb-1", "name": "Inbox", "kind": "mailbox", "writable": True}]),
    )
    monkeypatch.setattr(
        prefs.reminders_tools,
        "reminders_lists",
        Mock(
            return_value=[
                {
                    "id": "list-1",
                    "name": "Personal",
                    "kind": "reminder_list",
                    "writable": None,
                    "default_candidate": True,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        prefs.contacts_tools,
        "contacts_list_groups",
        Mock(
            return_value=[
                {
                    "id": "group-1",
                    "name": "Friends",
                    "kind": "contact_group",
                    "writable": None,
                    "default_candidate": True,
                }
            ]
        ),
    )
    monkeypatch.setattr(
        prefs.icloud_tools,
        "icloud_list",
        Mock(return_value=[{"id": "/Docs", "name": "Docs", "kind": "directory", "writable": True}]),
    )

    inventory = prefs.apple_inventory()

    assert [item["scope"] for item in inventory] == [
        "calendar",
        "mailbox",
        "reminder_list",
        "contact_group",
        "icloud",
    ]
    assert inventory[0]["id"] == "cal-1"
    assert inventory[-1]["name"] == "Docs"
    prefs.icloud_tools.icloud_list.assert_called_once_with("/")


def test_inventory_all_scopes_degrades_when_one_scope_fails(monkeypatch):
    monkeypatch.setattr(
        prefs.calendar_tools,
        "calendar_list_calendars",
        Mock(return_value=[{"id": "cal-1", "name": "Work", "kind": "calendar"}]),
    )
    monkeypatch.setattr(
        prefs.mail_tools,
        "mail_list_mailboxes",
        Mock(side_effect=RuntimeError("AppleScript failed (exit 1)")),
    )
    monkeypatch.setattr(prefs.reminders_tools, "reminders_lists", Mock(return_value=[]))
    monkeypatch.setattr(prefs.contacts_tools, "contacts_list_groups", Mock(return_value=[]))
    monkeypatch.setattr(prefs.icloud_tools, "icloud_list", Mock(return_value=[]))

    inventory = prefs.apple_inventory()

    assert inventory[0]["scope"] == "calendar"
    assert inventory[0]["id"] == "cal-1"
    assert inventory[1] == {
        "scope": "mailbox",
        "error": "inventory_scope_error",
        "message": "AppleScript failed (exit 1)",
    }


def test_preferences_round_trip_and_scope_view(monkeypatch, tmp_path):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_CONFIG_DIR", str(tmp_path))

    out = prefs.apple_preferences_set_default(
        "calendar",
        "cal-1",
        "Work",
        "calendar",
        "Primary",
    )
    assert out == {
        "scope": "calendar",
        "default": {
            "id": "cal-1",
            "name": "Work",
            "kind": "calendar",
            "account_name": "Primary",
            "path": None,
        },
    }

    alias_out = prefs.apple_preferences_add_alias(
        "calendar",
        "Home",
        "cal-1",
        "Work",
        "calendar",
        "Primary",
    )
    assert alias_out["alias"]["alias"] == "Home"
    assert alias_out["alias"]["target"]["id"] == "cal-1"

    scoped = prefs.apple_preferences_get("calendar")
    assert scoped["scope"] == "calendar"
    assert scoped["default"]["id"] == "cal-1"
    assert scoped["aliases"][0]["alias"] == "Home"

    full = prefs.apple_preferences_get()
    assert full["version"] == 1
    assert full["defaults"]["calendar"]["name"] == "Work"


def test_resolve_target_returns_structured_error_dict(monkeypatch, tmp_path):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(
        prefs.calendar_tools,
        "calendar_list_calendars",
        Mock(
            return_value=[
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
                    "writable": True,
                },
            ]
        ),
    )

    result = prefs.apple_resolve_target("calendar", query="Work", use_default=False)

    assert result["error"] == "target_ambiguous"
    assert result["scope"] == "calendar"
    assert len(result["candidates"]) == 2


def test_resolve_target_uses_default(monkeypatch, tmp_path):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(
        prefs.calendar_tools,
        "calendar_list_calendars",
        Mock(
            return_value=[
                {
                    "id": "cal-3",
                    "name": "Personal",
                    "kind": "calendar",
                    "account_name": "Primary",
                    "writable": True,
                }
            ]
        ),
    )

    prefs.apple_preferences_set_default(
        "calendar",
        "cal-3",
        "Personal",
        "calendar",
        "Primary",
    )

    result = prefs.apple_resolve_target("calendar", query=None)

    assert result["scope"] == "calendar"
    assert result["source"] == "default"
    assert result["target"]["id"] == "cal-3"
