from __future__ import annotations

import json
import os

import pytest

from apple_ecosystem_mcp.scheduled_tasks import (
    SCHEDULED_TASKS_SCHEMA_VERSION,
    ScheduledTaskReadOnlyError,
    ScheduledTaskStore,
    ScheduledTaskValidationError,
    ScheduledTasksDocument,
    get_scheduled_tasks_path,
)


def _sample_task(**overrides):
    task = {
        "name": "daily-briefing",
        "task_type": "daily_briefing",
        "schedule": {"kind": "daily", "time": "08:00"},
        "enabled": True,
        "config": {"calendar_alias": "work"},
        "output_path": "/tmp/daily-briefing.md",
        "metadata": {"created_by": "test"},
    }
    task.update(overrides)
    return task


def test_get_scheduled_tasks_path_uses_local_config_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_CONFIG_DIR", str(tmp_path))
    path = get_scheduled_tasks_path()
    assert path == tmp_path / "scheduled_tasks.json"


def test_store_loads_empty_document_when_missing(tmp_path):
    store = ScheduledTaskStore(tmp_path / "scheduled_tasks.json")
    document = store.load()
    assert isinstance(document, ScheduledTasksDocument)
    assert document.version == SCHEDULED_TASKS_SCHEMA_VERSION
    assert document.tasks == {}


def test_store_persists_task_and_enable_state(tmp_path):
    store = ScheduledTaskStore(tmp_path / "scheduled_tasks.json")
    store.create_task(_sample_task())
    store.set_enabled("daily-briefing", False)

    reloaded = store.load()
    task = reloaded.tasks["daily-briefing"]
    assert task.task_type == "daily_briefing"
    assert task.enabled is False
    assert task.schedule == {"kind": "daily", "time": "08:00"}
    assert task.config == {"calendar_alias": "work"}
    assert task.metadata == {"created_by": "test"}

    payload = json.loads((tmp_path / "scheduled_tasks.json").read_text(encoding="utf-8"))
    assert payload["version"] == SCHEDULED_TASKS_SCHEMA_VERSION
    assert payload["tasks"]["daily-briefing"]["enabled"] is False


def test_store_lists_only_enabled_tasks_when_requested(tmp_path):
    store = ScheduledTaskStore(tmp_path / "scheduled_tasks.json")
    store.create_task(_sample_task())
    store.create_task(
        _sample_task(
            name="tomorrow-preview",
            task_type="tomorrow_preview",
            enabled=False,
            output_path="/tmp/tomorrow-preview.md",
        )
    )

    enabled_names = [task.name for task in store.list_tasks(include_disabled=False)]
    all_names = [task.name for task in store.list_tasks()]

    assert enabled_names == ["daily-briefing"]
    assert sorted(all_names) == ["daily-briefing", "tomorrow-preview"]


def test_store_put_replaces_existing_task(tmp_path):
    store = ScheduledTaskStore(tmp_path / "scheduled_tasks.json")
    store.create_task(_sample_task())
    updated = store.put_task(_sample_task(enabled=False, schedule={"kind": "weekly", "weekday": "mon"}))

    assert updated.enabled is False
    assert updated.schedule == {"kind": "weekly", "weekday": "mon"}
    assert store.get_task("daily-briefing").schedule == {"kind": "weekly", "weekday": "mon"}


def test_create_rejects_duplicate_name(tmp_path):
    store = ScheduledTaskStore(tmp_path / "scheduled_tasks.json")
    store.create_task(_sample_task())

    with pytest.raises(ScheduledTaskValidationError, match="already exists"):
        store.create_task(_sample_task())


def test_delete_task_returns_flag(tmp_path):
    store = ScheduledTaskStore(tmp_path / "scheduled_tasks.json")
    store.create_task(_sample_task())

    assert store.delete_task("daily-briefing") is True
    assert store.delete_task("daily-briefing") is False


def test_validation_rejects_invalid_task_name(tmp_path):
    store = ScheduledTaskStore(tmp_path / "scheduled_tasks.json")

    with pytest.raises(ScheduledTaskValidationError, match="task name must match"):
        store.create_task(_sample_task(name="daily briefing"))


def test_validation_rejects_empty_schedule(tmp_path):
    store = ScheduledTaskStore(tmp_path / "scheduled_tasks.json")

    with pytest.raises(ScheduledTaskValidationError, match="schedule must not be empty"):
        store.create_task(_sample_task(schedule={}))


def test_validation_rejects_non_json_config_value(tmp_path):
    store = ScheduledTaskStore(tmp_path / "scheduled_tasks.json")

    with pytest.raises(ScheduledTaskValidationError, match="config must contain only JSON-compatible values"):
        store.create_task(_sample_task(config={"callback": object()}))


def test_load_rejects_invalid_json(tmp_path):
    path = tmp_path / "scheduled_tasks.json"
    path.write_text("{not json}\n", encoding="utf-8")
    store = ScheduledTaskStore(path)

    with pytest.raises(ScheduledTaskValidationError, match="Could not parse scheduled tasks JSON"):
        store.load()


def test_load_rejects_mismatched_task_key(tmp_path):
    path = tmp_path / "scheduled_tasks.json"
    path.write_text(
        json.dumps(
            {
                "version": SCHEDULED_TASKS_SCHEMA_VERSION,
                "tasks": {"stored-name": _sample_task(name="other-name")},
            }
        ),
        encoding="utf-8",
    )
    store = ScheduledTaskStore(path)

    with pytest.raises(ScheduledTaskValidationError, match="does not match task name"):
        store.load()


def test_store_raises_read_only_error_when_directory_is_unwritable(tmp_path):
    read_only_dir = tmp_path / "ro"
    read_only_dir.mkdir()
    os.chmod(read_only_dir, 0o555)
    try:
        store = ScheduledTaskStore(read_only_dir / "scheduled_tasks.json")
        with pytest.raises(ScheduledTaskReadOnlyError):
            store.create_task(_sample_task())
    finally:
        os.chmod(read_only_dir, 0o755)
