from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from apple_ecosystem_mcp import scheduler_cli
from apple_ecosystem_mcp.scheduled_tasks import ScheduledTaskStore


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


def test_schedule_list_prints_configured_tasks(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_CONFIG_DIR", str(tmp_path))
    store = ScheduledTaskStore(tmp_path / "scheduled_tasks.json")
    store.create_task(_sample_task())
    store.create_task(
        _sample_task(
            name="tomorrow-preview",
            task_type="tomorrow_preview",
            enabled=False,
            output_path=None,
        )
    )

    scheduler_cli.main(["list"])

    out = capsys.readouterr().out.strip().splitlines()
    assert out[0].startswith("daily-briefing [enabled] daily_briefing:")
    assert out[1].startswith("tomorrow-preview [disabled] tomorrow_preview:")


def test_schedule_run_calls_import_time_runner(monkeypatch):
    run_mock = Mock()
    run_mock.return_value = []
    monkeypatch.setattr(scheduler_cli, "run_scheduler", run_mock)

    scheduler_cli.main(["run"])

    run_mock.assert_called_once()


def test_schedule_run_can_target_named_task(monkeypatch):
    run_mock = Mock(return_value=[])
    monkeypatch.setattr(scheduler_cli, "run_scheduler", run_mock)

    scheduler_cli.main(["run", "daily-briefing"])

    run_mock.assert_called_once_with("daily-briefing")


def test_launch_agent_plist_is_rendered_deterministically(monkeypatch, tmp_path):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_LAUNCHAGENTS_DIR", str(tmp_path))
    monkeypatch.setattr(scheduler_cli.sys, "executable", "/usr/bin/python3")
    monkeypatch.setattr(scheduler_cli.sys, "frozen", False, raising=False)

    plist = scheduler_cli.build_launch_agent_plist()

    assert plist["Label"] == scheduler_cli.LAUNCHD_LABEL
    assert plist["ProgramArguments"] == [
        "/usr/bin/python3",
        "-m",
        "apple_ecosystem_mcp",
        "schedule",
        "run",
    ]
    assert plist["RunAtLoad"] is True
    assert plist["KeepAlive"] is True
    assert plist["StandardOutPath"] == str(
        Path(tmp_path) / f"{scheduler_cli.LAUNCHD_LABEL}.out.log"
    )
    assert plist["StandardErrorPath"] == str(
        Path(tmp_path) / f"{scheduler_cli.LAUNCHD_LABEL}.err.log"
    )

    rendered = scheduler_cli.render_launch_agent_plist()
    assert "<key>Label</key>" in rendered
    assert scheduler_cli.LAUNCHD_LABEL in rendered


def test_launch_agent_plist_uses_frozen_executable(monkeypatch, tmp_path):
    executable = tmp_path / "apple-ecosystem-mcp"
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_LAUNCHAGENTS_DIR", str(tmp_path))
    monkeypatch.setattr(scheduler_cli.sys, "executable", str(executable))
    monkeypatch.setattr(scheduler_cli.sys, "frozen", True, raising=False)

    plist = scheduler_cli.build_launch_agent_plist()

    assert plist["ProgramArguments"] == [str(executable), "schedule", "run"]


def test_schedule_install_writes_plist_and_bootstraps(monkeypatch, tmp_path):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_LAUNCHAGENTS_DIR", str(tmp_path))
    monkeypatch.setattr(scheduler_cli.sys, "executable", "/usr/bin/python3")
    launchctl_mock = Mock()
    monkeypatch.setattr(scheduler_cli, "_run_launchctl", launchctl_mock)

    plist_path = scheduler_cli.install_launchd_agent()

    assert plist_path == tmp_path / f"{scheduler_cli.LAUNCHD_LABEL}.plist"
    assert plist_path.exists()
    launchctl_mock.assert_called_once()
    assert "bootstrap" in launchctl_mock.call_args.args


def test_schedule_uninstall_bootouts_and_removes_plist(monkeypatch, tmp_path):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_LAUNCHAGENTS_DIR", str(tmp_path))
    plist_path = tmp_path / f"{scheduler_cli.LAUNCHD_LABEL}.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text("test", encoding="utf-8")
    launchctl_mock = Mock()
    monkeypatch.setattr(scheduler_cli, "_run_launchctl", launchctl_mock)

    removed_path = scheduler_cli.uninstall_launchd_agent(plist_path=plist_path)

    assert removed_path == plist_path
    assert not plist_path.exists()
    launchctl_mock.assert_called_once()
    assert "bootout" in launchctl_mock.call_args.args


def test_main_dispatches_schedule_subcommand(monkeypatch):
    schedule_mock = Mock()
    check_mock = Mock()
    run_mock = Mock()
    monkeypatch.setattr("apple_ecosystem_mcp.main.scheduler_cli.main", schedule_mock)
    monkeypatch.setattr("apple_ecosystem_mcp.main.check_permissions", check_mock)
    monkeypatch.setattr("apple_ecosystem_mcp.main.run", run_mock)
    monkeypatch.setattr(scheduler_cli.sys, "argv", ["apple-ecosystem-mcp", "schedule", "list"])

    from apple_ecosystem_mcp.main import main

    main()

    schedule_mock.assert_called_once_with(["list"])
    check_mock.assert_not_called()
    run_mock.assert_not_called()
