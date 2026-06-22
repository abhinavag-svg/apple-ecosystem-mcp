from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from mcp.types import ToolAnnotations

from ..scheduled_tasks import (
    ScheduledTaskError,
    ScheduledTaskReadOnlyError,
    ScheduledTaskStore,
    ScheduledTaskValidationError,
    get_scheduled_tasks_path,
)
from ..scheduler_runner import WorkflowRunError, run_scheduled_task_by_name
from ..server import mcp
from .actions import file_open_url, open_url_next_action, tool_next_action


def _store() -> ScheduledTaskStore:
    return ScheduledTaskStore(get_scheduled_tasks_path())


def _error(
    operation: str,
    exc: Exception,
    *,
    name: str | None = None,
) -> dict[str, Any]:
    if isinstance(exc, ScheduledTaskReadOnlyError):
        error = "scheduled_tasks_read_only_error"
    elif isinstance(exc, ScheduledTaskValidationError):
        error = "scheduled_tasks_validation_error"
    elif isinstance(exc, WorkflowRunError):
        error = "scheduled_tasks_run_error"
    elif isinstance(exc, ScheduledTaskError):
        error = "scheduled_tasks_error"
    else:
        error = "scheduled_tasks_error"

    payload: dict[str, Any] = {
        "error": error,
        "operation": operation,
        "message": str(exc),
    }
    if name is not None:
        payload["name"] = name
    return payload


def _task_payload(task) -> dict[str, Any]:
    payload = task.to_dict()
    payload["task_type"] = task.task_type
    if payload.get("name"):
        payload.setdefault(
            "next_action",
            tool_next_action(
                "scheduled_tasks_get",
                {"name": str(payload["name"])},
                label="View scheduled task",
            ),
        )
    return payload


def _run_payload(task_name: str, result) -> dict[str, Any]:
    output_path = Path(result.output_path)
    open_url = file_open_url(output_path)
    return {
        "task_name": task_name,
        "task_type": result.task_type,
        "output_path": str(output_path),
        "open_url": open_url,
        "open_action": open_url_next_action(open_url, label="Open report"),
        "content": result.content,
        "generated_at": result.generated_at.isoformat(),
        "success": True,
        "next_action": open_url_next_action(open_url, label="Open report"),
    }


@mcp.tool(annotations=ToolAnnotations(title="List Scheduled Tasks", readOnlyHint=True))
def scheduled_tasks_list(include_disabled: bool = True) -> dict[str, Any]:
    """List configured scheduled tasks."""
    store = _store()
    try:
        tasks = sorted(
            store.list_tasks(include_disabled=include_disabled),
            key=lambda task: task.name.casefold(),
        )
        return {
            "tasks": [_task_payload(task) for task in tasks],
            "count": len(tasks),
            "include_disabled": include_disabled,
        }
    except Exception as exc:  # pragma: no cover - exercised by structured-error tests
        return _error("list", exc)


@mcp.tool(annotations=ToolAnnotations(title="Get Scheduled Task", readOnlyHint=True))
def scheduled_tasks_get(name: str) -> dict[str, Any]:
    """Return a single scheduled task by name."""
    store = _store()
    try:
        task = store.get_task(name)
        if task is None:
            return {
                "error": "scheduled_tasks_not_found",
                "operation": "get",
                "name": name,
                "message": f"Scheduled task {name!r} does not exist",
            }
        return {"task": _task_payload(task)}
    except Exception as exc:  # pragma: no cover - exercised by structured-error tests
        return _error("get", exc, name=name)


@mcp.tool(annotations=ToolAnnotations(title="Create Scheduled Task"))
def scheduled_tasks_create(
    name: str,
    task_type: str,
    schedule: Mapping[str, Any],
    enabled: bool = True,
    config: Mapping[str, Any] | None = None,
    output_path: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create and persist a scheduled task."""
    store = _store()
    try:
        task = store.create_task(
            {
                "name": name,
                "task_type": task_type,
                "schedule": dict(schedule),
                "enabled": enabled,
                "config": dict(config or {}),
                "output_path": output_path,
                "metadata": dict(metadata or {}),
            }
        )
        return {"task": _task_payload(task), "created": True}
    except Exception as exc:  # pragma: no cover - exercised by structured-error tests
        return _error("create", exc, name=name)


@mcp.tool(annotations=ToolAnnotations(title="Run Scheduled Task"))
def scheduled_tasks_run(name: str) -> dict[str, Any]:
    """Run a scheduled task manually."""
    store = _store()
    try:
        result = run_scheduled_task_by_name(name, store=store)
        return _run_payload(name, result)
    except Exception as exc:  # pragma: no cover - exercised by structured-error tests
        return _error("run", exc, name=name)


@mcp.tool(annotations=ToolAnnotations(title="Enable Scheduled Task"))
def scheduled_tasks_enable(name: str) -> dict[str, Any]:
    """Enable a scheduled task."""
    store = _store()
    try:
        task = store.set_enabled(name, True)
        return {"task": _task_payload(task), "enabled": True}
    except Exception as exc:  # pragma: no cover - exercised by structured-error tests
        return _error("enable", exc, name=name)


@mcp.tool(annotations=ToolAnnotations(title="Disable Scheduled Task"))
def scheduled_tasks_disable(name: str) -> dict[str, Any]:
    """Disable a scheduled task."""
    store = _store()
    try:
        task = store.set_enabled(name, False)
        return {"task": _task_payload(task), "enabled": False}
    except Exception as exc:  # pragma: no cover - exercised by structured-error tests
        return _error("disable", exc, name=name)
