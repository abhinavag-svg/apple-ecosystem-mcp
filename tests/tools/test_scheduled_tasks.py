from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

from apple_ecosystem_mcp.scheduler_runner import WorkflowRunResult
from apple_ecosystem_mcp.tools import scheduled_tasks as scheduled_tools


def _inspect_tools(mcp):
    return {tool.name: tool for tool in mcp.local_provider._components.values()}


def _task_args(**overrides):
    payload = {
        "name": "daily-briefing",
        "task_type": "daily_briefing",
        "schedule": {"kind": "daily", "time": "08:00"},
        "enabled": True,
        "config": {"calendar_uid": "work"},
        "output_path": "reports/daily-briefing.md",
        "metadata": {"created_by": "test"},
    }
    payload.update(overrides)
    return payload


def test_scheduled_task_tools_registered_and_annotated():
    from apple_ecosystem_mcp import server

    tools = _inspect_tools(server.mcp)
    for name in [
        "scheduled_tasks_list",
        "scheduled_tasks_get",
        "scheduled_tasks_create",
        "scheduled_tasks_run",
        "scheduled_tasks_enable",
        "scheduled_tasks_disable",
    ]:
        assert name in tools
    assert tools["scheduled_tasks_list"].annotations.readOnlyHint is True
    assert tools["scheduled_tasks_get"].annotations.readOnlyHint is True


def test_scheduled_task_tool_round_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_CONFIG_DIR", str(tmp_path))

    created = scheduled_tools.scheduled_tasks_create(**_task_args())
    assert created["created"] is True
    assert created["task"]["name"] == "daily-briefing"

    listed = scheduled_tools.scheduled_tasks_list()
    assert listed["count"] == 1
    assert listed["tasks"][0]["name"] == "daily-briefing"

    fetched = scheduled_tools.scheduled_tasks_get("daily-briefing")
    assert fetched["task"]["task_type"] == "daily_briefing"
    assert fetched["task"]["enabled"] is True

    disabled = scheduled_tools.scheduled_tasks_disable("daily-briefing")
    assert disabled["enabled"] is False
    assert disabled["task"]["enabled"] is False

    enabled = scheduled_tools.scheduled_tasks_enable("daily-briefing")
    assert enabled["enabled"] is True
    assert enabled["task"]["enabled"] is True


def test_scheduled_task_run_returns_structured_result(monkeypatch, tmp_path):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(
        scheduled_tools,
        "run_scheduled_task_by_name",
        Mock(
            return_value=WorkflowRunResult(
                task_name="daily-briefing",
                task_type="daily_briefing",
                output_path=Path(tmp_path / "reports" / "daily-briefing.md"),
                content="# Daily Briefing\n",
                generated_at=datetime(2026, 6, 8, 9, 0, 0),
            )
        ),
    )

    result = scheduled_tools.scheduled_tasks_run("daily-briefing")

    assert {
        key: result[key]
        for key in (
            "task_name",
            "task_type",
            "output_path",
            "content",
            "generated_at",
            "success",
        )
    } == {
        "task_name": "daily-briefing",
        "task_type": "daily_briefing",
        "output_path": str(tmp_path / "reports" / "daily-briefing.md"),
        "content": "# Daily Briefing\n",
        "generated_at": "2026-06-08T09:00:00",
        "success": True,
    }
    assert result["open_url"].startswith("file://")
    assert result["open_action"]["type"] == "open_url"
    assert result["next_action"]["label"] == "Open report"


def test_scheduled_task_tools_return_structured_errors(monkeypatch, tmp_path):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_CONFIG_DIR", str(tmp_path))

    missing = scheduled_tools.scheduled_tasks_get("missing-task")
    assert missing["error"] == "scheduled_tasks_not_found"
    assert missing["operation"] == "get"

    invalid = scheduled_tools.scheduled_tasks_create(
        "bad-task",
        "daily_briefing",
        schedule={},
    )
    assert invalid["error"] == "scheduled_tasks_validation_error"
    assert invalid["operation"] == "create"

    monkeypatch.setattr(
        scheduled_tools,
        "run_scheduled_task_by_name",
        Mock(side_effect=RuntimeError("boom")),
    )
    run_error = scheduled_tools.scheduled_tasks_run("daily-briefing")
    assert run_error["error"] == "scheduled_tasks_error"
    assert run_error["operation"] == "run"
