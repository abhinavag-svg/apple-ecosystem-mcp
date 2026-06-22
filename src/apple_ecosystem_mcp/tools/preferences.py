from __future__ import annotations

from typing import Any

from mcp.types import ToolAnnotations

from ..preferences import PreferencesError, PreferencesStore, TargetPreference
from ..resolver import ResolverError, resolve_target
from . import calendar as calendar_tools
from . import contacts as contacts_tools
from . import icloud as icloud_tools
from . import mail as mail_tools
from . import reminders as reminders_tools
from .actions import tool_next_action
from ..server import mcp

_KNOWN_SCOPES = {
    "calendar",
    "mailbox",
    "reminder_list",
    "contact_group",
    "icloud",
}


def _store() -> PreferencesStore:
    return PreferencesStore()


def _target_from_parts(
    id: str,
    name: str,
    kind: str,
    account_name: str | None = None,
    path: str | None = None,
) -> TargetPreference:
    return TargetPreference(
        id=str(id),
        name=str(name),
        kind=str(kind),
        account_name=account_name,
        path=path,
    )


def _preferences_error(scope: str | None, exc: Exception) -> dict[str, Any]:
    payload: dict[str, Any] = {"error": "preferences_error", "message": str(exc)}
    if scope is not None:
        payload["scope"] = scope
    return payload


def _inventory_scope_error(scope: str, exc: Exception) -> dict[str, Any]:
    return {
        "scope": scope,
        "error": "inventory_scope_error",
        "message": str(exc),
    }


def _load_inventory_scope(scope: str) -> list[dict[str, Any]]:
    if scope == "calendar":
        rows = calendar_tools.calendar_list_calendars()
    elif scope == "mailbox":
        rows = mail_tools.mail_list_mailboxes()
    elif scope == "reminder_list":
        rows = reminders_tools.reminders_lists(include_metadata=True)
    elif scope == "contact_group":
        rows = contacts_tools.contacts_list_groups(include_metadata=True)
    elif scope == "icloud":
        rows = icloud_tools.icloud_list("/")
    else:
        raise ValueError(f"Unknown inventory scope {scope!r}")
    return [dict(item, scope=scope) for item in rows]


def _inventory_rows(scope: str | None = None) -> list[dict[str, Any]] | dict[str, Any]:
    if scope is not None and scope not in _KNOWN_SCOPES:
        return {
            "error": "inventory_scope_unknown",
            "scope": scope,
            "available_scopes": sorted(_KNOWN_SCOPES),
        }

    try:
        if scope is not None:
            return _load_inventory_scope(scope)
    except PreferencesError as exc:
        return _preferences_error(scope, exc)
    except Exception as exc:
        return {"error": "inventory_error", "message": str(exc), "scope": scope}

    rows: list[dict[str, Any]] = []
    for scope_name in ("calendar", "mailbox", "reminder_list", "contact_group", "icloud"):
        try:
            rows.extend(_load_inventory_scope(scope_name))
        except Exception as exc:
            rows.append(_inventory_scope_error(scope_name, exc))
    return rows


def _scope_preferences_view(store: PreferencesStore, scope: str) -> dict[str, Any]:
    document = store.load()
    default = document.defaults.get(scope)
    aliases = document.aliases.get(scope, {})
    return {
        "scope": scope,
        "default": default.to_dict() if default is not None else None,
        "aliases": [record.to_dict() for record in sorted(aliases.values(), key=lambda record: record.alias.casefold())],
    }


def _preferences_get_action(scope: str) -> dict[str, Any]:
    return tool_next_action(
        "apple_preferences_get",
        {"scope": scope},
        label="View preferences",
    )


@mcp.tool(annotations=ToolAnnotations(title="Apple Inventory", readOnlyHint=True))
def apple_inventory(scope: str | None = None) -> list[dict[str, Any]] | dict[str, Any]:
    """List discoverable Apple containers across supported scopes."""
    return _inventory_rows(scope)


@mcp.tool(annotations=ToolAnnotations(title="Get Apple Preferences", readOnlyHint=True))
def apple_preferences_get(scope: str | None = None) -> dict[str, Any]:
    """Return persisted preferences, optionally filtered to a scope."""
    store = _store()
    try:
        if scope is None:
            return store.load().to_dict()
        return _scope_preferences_view(store, scope)
    except PreferencesError as exc:
        return _preferences_error(scope, exc)


@mcp.tool(annotations=ToolAnnotations(title="Set Apple Default Preference"))
def apple_preferences_set_default(
    scope: str,
    id: str,
    name: str,
    kind: str,
    account_name: str | None = None,
    path: str | None = None,
) -> dict[str, Any]:
    """Set the default target for a scope."""
    store = _store()
    try:
        target = _target_from_parts(id=id, name=name, kind=kind, account_name=account_name, path=path)
        preference = store.set_default(scope, target)
        return {"scope": scope, "default": preference.to_dict(), "next_action": _preferences_get_action(scope)}
    except PreferencesError as exc:
        return _preferences_error(scope, exc)
    except Exception as exc:
        return _preferences_error(scope, exc)


@mcp.tool(annotations=ToolAnnotations(title="Add Apple Alias"))
def apple_preferences_add_alias(
    scope: str,
    alias: str,
    id: str,
    name: str,
    kind: str,
    account_name: str | None = None,
    path: str | None = None,
) -> dict[str, Any]:
    """Add an alias for a scope target."""
    store = _store()
    try:
        target = _target_from_parts(id=id, name=name, kind=kind, account_name=account_name, path=path)
        record = store.add_alias(scope, alias, target)
        return {"scope": scope, "alias": record.to_dict(), "next_action": _preferences_get_action(scope)}
    except PreferencesError as exc:
        return _preferences_error(scope, exc)
    except Exception as exc:
        return _preferences_error(scope, exc)


@mcp.tool(annotations=ToolAnnotations(title="Remove Apple Alias", destructiveHint=True))
def apple_preferences_remove_alias(scope: str, alias: str) -> dict[str, Any]:
    """Remove an alias for a scope target."""
    store = _store()
    try:
        removed = store.remove_alias(scope, alias)
        return {"scope": scope, "alias": alias, "removed": removed, "next_action": _preferences_get_action(scope)}
    except PreferencesError as exc:
        return _preferences_error(scope, exc)
    except Exception as exc:
        return _preferences_error(scope, exc)


@mcp.tool(annotations=ToolAnnotations(title="Resolve Apple Target", readOnlyHint=True))
def apple_resolve_target(
    scope: str,
    query: str | None = None,
    require_writable: bool = False,
    use_default: bool = True,
) -> dict[str, Any]:
    """Resolve a friendly target name against the current inventory and preferences."""
    inventory = _inventory_rows(scope)
    if isinstance(inventory, dict):
        return inventory

    try:
        resolved = resolve_target(
            query,
            inventory,
            scope=scope,
            preferences=_store(),
            require_writable=require_writable,
            use_default=use_default,
        )
        return resolved.to_dict()
    except ResolverError as exc:
        return exc.to_dict()
    except PreferencesError as exc:
        return _preferences_error(scope, exc)
    except Exception as exc:
        return {"error": "resolver_error", "scope": scope, "query": query, "message": str(exc)}
