from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

APP_NAME = "apple-ecosystem-mcp"
SCHEDULED_TASKS_SCHEMA_VERSION = 1

TASK_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")

JSONScalar = str | int | float | bool | None
JSONValue = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]


class ScheduledTaskError(RuntimeError):
    """Base class for scheduled task storage and validation errors."""


class ScheduledTaskReadOnlyError(ScheduledTaskError):
    """Raised when scheduled task config cannot be written."""


class ScheduledTaskValidationError(ScheduledTaskError):
    """Raised when scheduled task configuration is invalid."""


class UnknownTaskTypeError(ScheduledTaskValidationError):
    """Raised when a task type is not registered."""


class ScheduledTaskSafetyError(ScheduledTaskValidationError):
    """Raised when a task type violates scheduler safety policy."""


def get_scheduled_tasks_path() -> Path:
    """Return the local scheduled task config path outside the repo."""
    override = os.environ.get("APPLE_ECOSYSTEM_MCP_CONFIG_DIR")
    if override:
        return Path(override).expanduser() / "scheduled_tasks.json"

    home = Path.home()
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
    elif os.name == "posix" and _sys_platform() == "darwin":
        base = home / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config"))

    return base / APP_NAME / "scheduled_tasks.json"


def _sys_platform() -> str:
    return os.environ.get("APPLE_ECOSYSTEM_MCP_PLATFORM", os.sys.platform)


def _require_non_empty_string(value: Any, *, field_name: str) -> str:
    text = str(value).strip()
    if not text:
        raise ScheduledTaskValidationError(f"{field_name} must not be empty")
    return text


def _validate_task_name(value: Any) -> str:
    name = _require_non_empty_string(value, field_name="task name")
    if not TASK_NAME_PATTERN.fullmatch(name):
        raise ScheduledTaskValidationError(
            "task name must match ^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$"
        )
    return name


def _validate_json_value(value: Any, *, field_name: str) -> JSONValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, list):
        return [_validate_json_value(item, field_name=field_name) for item in value]

    if isinstance(value, Mapping):
        normalized: dict[str, JSONValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ScheduledTaskValidationError(f"{field_name} keys must be strings")
            normalized[key] = _validate_json_value(item, field_name=field_name)
        return normalized

    raise ScheduledTaskValidationError(
        f"{field_name} must contain only JSON-compatible values"
    )


def _validate_mapping(
    value: Mapping[str, Any] | None,
    *,
    field_name: str,
    allow_empty: bool,
) -> dict[str, JSONValue]:
    if value is None:
        return {}

    normalized = _validate_json_value(value, field_name=field_name)
    assert isinstance(normalized, dict)
    if not allow_empty and not normalized:
        raise ScheduledTaskValidationError(f"{field_name} must not be empty")
    return normalized


@dataclass(frozen=True)
class ScheduledTaskType:
    """Definition for a scheduler-recognized task type."""

    name: str
    description: str
    destructive: bool = False
    supports_schedule: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _require_non_empty_string(self.name, field_name="task type name"))
        object.__setattr__(
            self,
            "description",
            _require_non_empty_string(self.description, field_name="task type description"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "destructive": self.destructive,
            "supports_schedule": self.supports_schedule,
        }


def is_destructive_task_type(task_type: ScheduledTaskType) -> bool:
    """Return whether the task type is unsafe for scheduled execution."""
    return task_type.destructive


def ensure_safe_task_type(task_type: ScheduledTaskType) -> ScheduledTaskType:
    """Raise when a task type is destructive and therefore unschedulable."""
    if is_destructive_task_type(task_type):
        raise ScheduledTaskSafetyError(
            f"Scheduled task type {task_type.name!r} is destructive and cannot be registered"
        )
    return task_type


def default_task_registry() -> "ScheduledTaskRegistry":
    """Return the built-in registry of safe scheduled task types."""
    registry = ScheduledTaskRegistry()
    for task_type in (
        ScheduledTaskType(
            name="daily_briefing",
            description="Read-only daily report across mail, calendar, and reminders.",
        ),
        ScheduledTaskType(
            name="tomorrow_preview",
            description="Read-only tomorrow preview report for upcoming commitments.",
        ),
        ScheduledTaskType(
            name="overdue_reminders_review",
            description="Read-only report of overdue reminders and suggested triage.",
        ),
        ScheduledTaskType(
            name="unread_priority_mail_review",
            description="Read-only report of unread priority mail and follow-up candidates.",
        ),
        ScheduledTaskType(
            name="receipt_finder",
            description="Read-only receipt search workflow that produces a local report.",
        ),
        ScheduledTaskType(
            name="weekly_planning_digest",
            description="Read-only weekly planning digest across supported Apple apps.",
        ),
    ):
        registry.register(task_type)
    return registry


@dataclass
class ScheduledTaskRegistry:
    """Allowed scheduled task types, limited to non-destructive definitions."""

    task_types: dict[str, ScheduledTaskType] = field(default_factory=dict)

    def register(self, task_type: ScheduledTaskType) -> ScheduledTaskType:
        safe_task_type = ensure_safe_task_type(task_type)
        self.task_types[safe_task_type.name] = safe_task_type
        return safe_task_type

    def get(self, name: str) -> ScheduledTaskType | None:
        return self.task_types.get(name)

    def require(self, name: str) -> ScheduledTaskType:
        task_type = self.get(name)
        if task_type is None:
            raise UnknownTaskTypeError(f"Unknown scheduled task type {name!r}")
        return ensure_safe_task_type(task_type)

    def list(self) -> list[ScheduledTaskType]:
        return [self.task_types[name] for name in sorted(self.task_types)]

    def names(self) -> list[str]:
        return [task_type.name for task_type in self.list()]


@dataclass(frozen=True)
class ScheduledTask:
    """Persisted scheduled task configuration."""

    name: str
    task_type: str
    schedule: dict[str, JSONValue]
    enabled: bool = True
    config: dict[str, JSONValue] = field(default_factory=dict)
    output_path: str | None = None
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, Any],
        *,
        registry: ScheduledTaskRegistry | None = None,
    ) -> "ScheduledTask":
        task = cls(
            name=_validate_task_name(data.get("name")),
            task_type=_require_non_empty_string(data.get("task_type"), field_name="task_type"),
            schedule=_validate_mapping(
                _mapping_or_none(data.get("schedule"), field_name="schedule"),
                field_name="schedule",
                allow_empty=False,
            ),
            enabled=_coerce_bool(data.get("enabled", True), field_name="enabled"),
            config=_validate_mapping(
                _mapping_or_none(data.get("config"), field_name="config"),
                field_name="config",
                allow_empty=True,
            ),
            output_path=_optional_string(data.get("output_path"), field_name="output_path"),
            metadata=_validate_mapping(
                _mapping_or_none(data.get("metadata"), field_name="metadata"),
                field_name="metadata",
                allow_empty=True,
            ),
        )
        if registry is not None:
            registry.require(task.task_type)
        return task

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "task_type": self.task_type,
            "schedule": self.schedule,
            "enabled": self.enabled,
            "config": self.config,
            "output_path": self.output_path,
            "metadata": self.metadata,
        }

    def with_enabled(self, enabled: bool) -> "ScheduledTask":
        return ScheduledTask(
            name=self.name,
            task_type=self.task_type,
            schedule=dict(self.schedule),
            enabled=enabled,
            config=dict(self.config),
            output_path=self.output_path,
            metadata=dict(self.metadata),
        )


@dataclass
class ScheduledTasksDocument:
    version: int = SCHEDULED_TASKS_SCHEMA_VERSION
    tasks: dict[str, ScheduledTask] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> "ScheduledTasksDocument":
        return cls()

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        registry: ScheduledTaskRegistry | None = None,
    ) -> "ScheduledTasksDocument":
        version = int(data.get("version", SCHEDULED_TASKS_SCHEMA_VERSION))
        if version != SCHEDULED_TASKS_SCHEMA_VERSION:
            raise ScheduledTaskValidationError(
                "Unsupported scheduled task schema version "
                f"{version}; expected {SCHEDULED_TASKS_SCHEMA_VERSION}"
            )

        raw_tasks = data.get("tasks", {})
        if not isinstance(raw_tasks, Mapping):
            raise ScheduledTaskValidationError("tasks must be a JSON object")

        tasks: dict[str, ScheduledTask] = {}
        for name, task_data in raw_tasks.items():
            if not isinstance(task_data, Mapping):
                raise ScheduledTaskValidationError(f"scheduled task {name!r} must be a JSON object")
            task = ScheduledTask.from_mapping(task_data, registry=registry)
            if task.name != name:
                raise ScheduledTaskValidationError(
                    f"scheduled task key {name!r} does not match task name {task.name!r}"
                )
            tasks[name] = task
        return cls(version=version, tasks=tasks)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "tasks": {name: task.to_dict() for name, task in sorted(self.tasks.items())},
        }


class ScheduledTaskStore:
    """Versioned JSON storage for local scheduled task configuration."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        registry: ScheduledTaskRegistry | None = None,
    ) -> None:
        self.path = Path(path).expanduser() if path is not None else get_scheduled_tasks_path()
        self.registry = registry or default_task_registry()

    def load(self) -> ScheduledTasksDocument:
        if not self.path.exists():
            return ScheduledTasksDocument.empty()

        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise ScheduledTaskError(f"Could not read scheduled tasks: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise ScheduledTaskValidationError(
                f"Could not parse scheduled tasks JSON: {exc}"
            ) from exc

        if not isinstance(raw, Mapping):
            raise ScheduledTaskValidationError("Scheduled task file must contain a JSON object")
        return ScheduledTasksDocument.from_dict(raw, registry=self.registry)

    def save(self, document: ScheduledTasksDocument) -> ScheduledTasksDocument:
        self._ensure_parent_dir()
        payload = json.dumps(document.to_dict(), indent=2, sort_keys=True) + "\n"
        try:
            self.path.write_text(payload, encoding="utf-8")
        except OSError as exc:
            raise ScheduledTaskReadOnlyError(f"Could not write scheduled tasks: {exc}") from exc
        return document

    def list_tasks(self, *, include_disabled: bool = True) -> list[ScheduledTask]:
        tasks = self.load().tasks.values()
        if include_disabled:
            return list(tasks)
        return [task for task in tasks if task.enabled]

    def get_task(self, name: str) -> ScheduledTask | None:
        return self.load().tasks.get(name)

    def create_task(self, task: ScheduledTask | Mapping[str, Any]) -> ScheduledTask:
        document = self.load()
        scheduled_task = self._coerce_task(task)
        if scheduled_task.name in document.tasks:
            raise ScheduledTaskValidationError(
                f"Scheduled task {scheduled_task.name!r} already exists"
            )
        document.tasks[scheduled_task.name] = scheduled_task
        self.save(document)
        return scheduled_task

    def put_task(self, task: ScheduledTask | Mapping[str, Any]) -> ScheduledTask:
        document = self.load()
        scheduled_task = self._coerce_task(task)
        document.tasks[scheduled_task.name] = scheduled_task
        self.save(document)
        return scheduled_task

    def set_enabled(self, name: str, enabled: bool) -> ScheduledTask:
        document = self.load()
        task = document.tasks.get(name)
        if task is None:
            raise ScheduledTaskValidationError(f"Scheduled task {name!r} does not exist")
        updated = task.with_enabled(enabled)
        document.tasks[name] = updated
        self.save(document)
        return updated

    def delete_task(self, name: str) -> bool:
        document = self.load()
        existed = name in document.tasks
        document.tasks.pop(name, None)
        if existed:
            self.save(document)
        return existed

    def _coerce_task(self, task: ScheduledTask | Mapping[str, Any]) -> ScheduledTask:
        if isinstance(task, ScheduledTask):
            self.registry.require(task.task_type)
            return task
        return ScheduledTask.from_mapping(task, registry=self.registry)

    def _ensure_parent_dir(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ScheduledTaskReadOnlyError(
                f"Could not create scheduled task directory: {exc}"
            ) from exc


def _mapping_or_none(value: Any, *, field_name: str) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ScheduledTaskValidationError(f"{field_name} must be a JSON object")
    return value


def _coerce_bool(value: Any, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    raise ScheduledTaskValidationError(f"{field_name} must be a boolean")


def _optional_string(value: Any, *, field_name: str) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        raise ScheduledTaskValidationError(f"{field_name} must not be blank")
    return text
