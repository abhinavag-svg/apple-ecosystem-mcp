from __future__ import annotations

import json

import pytest

from apple_ecosystem_mcp.scheduled_tasks import (
    ScheduledTaskSafetyError,
    ScheduledTaskStore,
    ScheduledTaskType,
    ScheduledTaskValidationError,
    ScheduledTaskRegistry,
    UnknownTaskTypeError,
    default_task_registry,
    ensure_safe_task_type,
    is_destructive_task_type,
)


def test_default_registry_contains_only_expected_safe_task_types():
    registry = default_task_registry()

    assert registry.names() == [
        "daily_briefing",
        "overdue_reminders_review",
        "receipt_finder",
        "tomorrow_preview",
        "unread_priority_mail_review",
        "weekly_planning_digest",
    ]


def test_registry_rejects_destructive_task_types():
    registry = ScheduledTaskRegistry()

    with pytest.raises(ScheduledTaskSafetyError, match="destructive"):
        registry.register(
            ScheduledTaskType(
                name="delete_mail",
                description="Deletes messages automatically.",
                destructive=True,
            )
        )


def test_safety_helpers_flag_destructive_task_types():
    task_type = ScheduledTaskType(
        name="archive_mail",
        description="Archives mail automatically.",
        destructive=True,
    )

    assert is_destructive_task_type(task_type) is True
    with pytest.raises(ScheduledTaskSafetyError, match="cannot be registered"):
        ensure_safe_task_type(task_type)


def test_store_rejects_unknown_task_type(tmp_path):
    store = ScheduledTaskStore(tmp_path / "scheduled_tasks.json")

    with pytest.raises(UnknownTaskTypeError, match="Unknown scheduled task type"):
        store.create_task(
            {
                "name": "cleanup-mail",
                "task_type": "cleanup_mail",
                "schedule": {"kind": "daily", "time": "18:00"},
            }
        )


def test_store_rejects_destructive_task_type_loaded_from_disk(tmp_path):
    path = tmp_path / "scheduled_tasks.json"
    registry = ScheduledTaskRegistry()
    registry.task_types["delete_mail"] = ScheduledTaskType(
        name="delete_mail",
        description="Deletes messages automatically.",
        destructive=True,
    )
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "tasks": {
                    "cleanup-mail": {
                        "name": "cleanup-mail",
                        "task_type": "delete_mail",
                        "schedule": {"kind": "daily", "time": "18:00"},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    store = ScheduledTaskStore(path, registry=registry)
    with pytest.raises(ScheduledTaskSafetyError, match="destructive"):
        store.load()


def test_store_rejects_non_boolean_enabled_field(tmp_path):
    store = ScheduledTaskStore(tmp_path / "scheduled_tasks.json")

    with pytest.raises(ScheduledTaskValidationError, match="enabled must be a boolean"):
        store.create_task(
            {
                "name": "daily-briefing",
                "task_type": "daily_briefing",
                "schedule": {"kind": "daily", "time": "08:00"},
                "enabled": "yes",
            }
        )
