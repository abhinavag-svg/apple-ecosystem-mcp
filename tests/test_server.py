from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import Mock

import pytest


def _inspect_tools(mcp):
    # FastMCP 3.x stores tools in local_provider._components
    # Keys are 'tool:{name}@' format, values are FunctionTool objects
    return {tool.name: tool for tool in mcp.local_provider._components.values()}

def test_importing_server_registers_all_tool_modules():
    from apple_ecosystem_mcp import server

    tools = _inspect_tools(server.mcp)

    assert "hello_apple" in tools
    # Placeholder tools should register at import time via tools/init.py.
    assert "mail_search" in tools
    assert "calendar_list_calendars" in tools
    assert "contacts_search" in tools
    assert "reminders_lists" in tools
    assert "icloud_list" in tools


def test_hello_apple_is_registered_and_delegates(monkeypatch):
    from apple_ecosystem_mcp import server

    run_mock = Mock(return_value="14.0")
    monkeypatch.setattr(server, "run_applescript", run_mock)
    assert server.hello_apple() == "14.0"
    run_mock.assert_called_once_with("return system version of (system info)")


def test_readonly_and_destructive_annotations_present():
    from apple_ecosystem_mcp import server

    tools = _inspect_tools(server.mcp)
    assert tools["hello_apple"].annotations.readOnlyHint is True
    assert tools["mail_search"].annotations.readOnlyHint is True
    assert tools["icloud_delete"].annotations.destructiveHint is True
    assert tools["calendar_delete_event"].annotations.destructiveHint is True


def test_no_tool_definitions_use_varargs_or_kwargs():
    tools_dir = Path(__file__).resolve().parents[1] / "src" / "apple_ecosystem_mcp" / "tools"
    for path in [
        tools_dir / "mail.py",
        tools_dir / "calendar.py",
        tools_dir / "contacts.py",
        tools_dir / "reminders.py",
        tools_dir / "icloud.py",
    ]:
        module = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in module.body:
            if isinstance(node, ast.FunctionDef):
                assert node.args.vararg is None
                assert node.args.kwarg is None
