from __future__ import annotations

from pathlib import Path
from typing import Any


def tool_next_action(tool: str, arguments: dict[str, Any], *, label: str) -> dict[str, Any]:
    return {
        "type": "tool_call",
        "tool": tool,
        "arguments": arguments,
        "label": label,
    }


def open_url_next_action(url: str, *, label: str) -> dict[str, Any]:
    return {
        "type": "open_url",
        "open_url": url,
        "label": label,
    }


def open_app_next_action(app: str, *, label: str | None = None) -> dict[str, Any]:
    return {
        "type": "open_app",
        "app": app,
        "label": label or f"Open {app}",
        "command": ["open", "-a", app],
    }


def terminal_command_next_action(command: str, *, label: str) -> dict[str, Any]:
    return {
        "type": "terminal_command",
        "command": command,
        "label": label,
    }


def file_open_url(path: Path) -> str:
    return path.resolve().as_uri()

