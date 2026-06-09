from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from apple_ecosystem_mcp.scheduler_runner import (
    SUPPORTED_WORKFLOW_NAMES,
    SchedulerRunner,
    WorkflowConnectors,
    WorkflowRunError,
    resolve_output_path,
    run_scheduled_task_by_name,
)
from apple_ecosystem_mcp.scheduled_tasks import ScheduledTask, ScheduledTaskStore


class StubConnectors:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def calendar_list_events(self, start: str, end: str, calendar_uid: str | None = None, limit: int = 0):
        self.calls.append(
            ("calendar_list_events", {"start": start, "end": end, "calendar_uid": calendar_uid, "limit": limit})
        )
        return [
            {
                "title": "Standup",
                "start": "2026-06-08T09:00:00",
                "end": "2026-06-08T09:15:00",
                "calendar_name": "Work",
                "location": "Zoom",
            }
        ]

    def mail_search(
        self,
        query: str,
        mailbox_id: str | None = None,
        limit: int = 0,
        since: str | None = None,
        before: str | None = None,
        search_fields: list[str] | None = None,
        filters: dict | None = None,
    ):
        self.calls.append(
            (
                "mail_search",
                {
                    "query": query,
                    "mailbox_id": mailbox_id,
                    "limit": limit,
                    "since": since,
                    "before": before,
                    "search_fields": search_fields,
                    "filters": filters,
                },
            )
        )
        return [
            {
                "subject": "Receipt for lunch",
                "sender": "billing@example.com",
                "date": "2026-06-08T08:30:00",
                "preview": "Receipt attached",
            }
        ]

    def reminders_lists(self, include_metadata: bool = False):
        self.calls.append(("reminders_lists", {"include_metadata": include_metadata}))
        return [{"id": "work-list", "name": "Work"}]

    def reminders_list(
        self,
        list_name: str | None = None,
        completed: bool = False,
        reminders_list_id: str | None = None,
        limit: int = 20,
    ):
        self.calls.append(
            (
                "reminders_list",
                {
                    "list_name": list_name,
                    "completed": completed,
                    "reminders_list_id": reminders_list_id,
                    "limit": limit,
                },
            )
        )
        return [
            {
                "title": "File expenses",
                "due": "2026-06-07T17:00:00",
                "list_name": "Work",
            },
            {
                "title": "Prep for meeting",
                "due": "2026-06-09T10:00:00",
                "list_name": "Work",
            },
        ]

    def icloud_search(self, query: str, path: str = "/", content_search: bool = False):
        self.calls.append(("icloud_search", {"query": query, "path": path, "content_search": content_search}))
        return [{"name": "receipt.pdf", "path": "/Finance/receipt.pdf", "kind": "file"}]


def _bundle(stubs: StubConnectors) -> WorkflowConnectors:
    return WorkflowConnectors(
        calendar_list_events=stubs.calendar_list_events,
        mail_search=stubs.mail_search,
        reminders_lists=stubs.reminders_lists,
        reminders_list=stubs.reminders_list,
        icloud_search=stubs.icloud_search,
    )


def _task(task_type: str, tmp_path: Path, **config) -> ScheduledTask:
    return ScheduledTask(
        name=f"{task_type}-task",
        task_type=task_type,
        schedule={"kind": "manual"},
        config=config,
        output_path=str(tmp_path / f"{task_type}.md"),
    )


@pytest.mark.parametrize("task_type", SUPPORTED_WORKFLOW_NAMES)
def test_runner_supports_all_expected_workflows(tmp_path, task_type):
    stubs = StubConnectors()
    runner = SchedulerRunner(connectors=_bundle(stubs))

    result = runner.run_task(_task(task_type, tmp_path), now=datetime(2026, 6, 8, 8, 0, 0))

    assert result.output_path.exists()
    assert result.task_type == task_type
    assert f"Workflow: `{task_type}`" in result.content


def test_default_output_path_uses_config_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_CONFIG_DIR", str(tmp_path / "config"))
    task = ScheduledTask(
        name="daily-briefing",
        task_type="daily_briefing",
        schedule={"kind": "manual"},
    )

    path = resolve_output_path(task)

    assert path == tmp_path / "config" / "scheduled-task-reports" / "daily-briefing.md"


def test_runner_writes_markdown_report_to_default_path(monkeypatch, tmp_path):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_CONFIG_DIR", str(tmp_path / "config"))
    stubs = StubConnectors()
    runner = SchedulerRunner(connectors=_bundle(stubs))
    task = ScheduledTask(name="briefing", task_type="daily_briefing", schedule={"kind": "manual"})

    result = runner.run_task(task, now=datetime(2026, 6, 8, 8, 0, 0))

    assert result.output_path == tmp_path / "config" / "scheduled-task-reports" / "briefing.md"
    assert "# Daily Briefing" in result.output_path.read_text(encoding="utf-8")


def test_runner_can_load_task_from_store(tmp_path):
    stubs = StubConnectors()
    store = ScheduledTaskStore(tmp_path / "scheduled_tasks.json")
    store.create_task(
        {
            "name": "daily-briefing",
            "task_type": "daily_briefing",
            "schedule": {"kind": "manual"},
            "output_path": str(tmp_path / "daily-briefing.md"),
        }
    )

    result = run_scheduled_task_by_name(
        "daily-briefing",
        store=store,
        now=datetime(2026, 6, 8, 8, 0, 0),
        connectors=_bundle(stubs),
    )

    assert result.output_path.exists()
    assert "Daily Briefing" in result.content


def test_receipt_finder_uses_only_mail_and_icloud(tmp_path):
    stubs = StubConnectors()
    runner = SchedulerRunner(connectors=_bundle(stubs))

    runner.run_task(_task("receipt_finder", tmp_path), now=datetime(2026, 6, 8, 8, 0, 0))

    assert [name for name, _payload in stubs.calls] == ["mail_search", "icloud_search"]


def test_overdue_review_uses_only_reminders(tmp_path):
    stubs = StubConnectors()
    runner = SchedulerRunner(connectors=_bundle(stubs))

    runner.run_task(_task("overdue_reminders_review", tmp_path), now=datetime(2026, 6, 8, 8, 0, 0))

    assert [name for name, _payload in stubs.calls] == ["reminders_lists", "reminders_list"]


def test_runner_rejects_unknown_workflow(tmp_path):
    stubs = StubConnectors()
    runner = SchedulerRunner(connectors=_bundle(stubs))
    task = ScheduledTask(
        name="mystery-task",
        task_type="mystery_workflow",
        schedule={"kind": "manual"},
        output_path=str(tmp_path / "mystery.md"),
    )

    with pytest.raises(WorkflowRunError, match="Unsupported scheduled workflow"):
        runner.run_task(task)
