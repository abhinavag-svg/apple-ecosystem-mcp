from __future__ import annotations

import argparse
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from .scheduled_tasks import ScheduledTaskStore, default_task_registry, get_scheduled_tasks_path

LAUNCHD_LABEL = "com.apple-ecosystem-mcp.scheduler"
LAUNCHD_AGENT_DIR_ENV = "APPLE_ECOSYSTEM_MCP_LAUNCHAGENTS_DIR"

try:  # pragma: no cover - exercised indirectly when a runner module exists later
    from .scheduler_runner import run_scheduler
except ImportError:  # pragma: no cover - import-time fallback is the expected current path

    def run_scheduler(name: str | None = None) -> None:
        raise RuntimeError("scheduler_runner.py is not available yet")


def get_launch_agent_plist_path() -> Path:
    override = os.environ.get(LAUNCHD_AGENT_DIR_ENV)
    base_dir = Path(override).expanduser() if override else Path.home() / "Library" / "LaunchAgents"
    return base_dir / f"{LAUNCHD_LABEL}.plist"


def build_launch_agent_plist() -> dict[str, object]:
    if getattr(sys, "frozen", False):
        program_arguments = [sys.executable, "schedule", "run"]
    else:
        program_arguments = [sys.executable, "-m", "apple_ecosystem_mcp", "schedule", "run"]
    return {
        "Label": LAUNCHD_LABEL,
        "ProgramArguments": program_arguments,
        "RunAtLoad": True,
        "KeepAlive": True,
        "StandardOutPath": str(get_launch_agent_plist_path().with_suffix(".out.log")),
        "StandardErrorPath": str(get_launch_agent_plist_path().with_suffix(".err.log")),
    }


def render_launch_agent_plist() -> str:
    return plistlib.dumps(build_launch_agent_plist(), fmt=plistlib.FMT_XML, sort_keys=False).decode(
        "utf-8"
    )


def list_scheduled_tasks() -> list[str]:
    store = ScheduledTaskStore(get_scheduled_tasks_path())
    registry = default_task_registry()
    tasks = store.list_tasks()

    if not tasks:
        return ["No scheduled tasks configured."]

    lines = []
    for task in sorted(tasks, key=lambda item: item.name):
        task_type = registry.get(task.task_type)
        description = task_type.description if task_type is not None else task.task_type
        schedule_text = json.dumps(task.schedule, sort_keys=True)
        state = "enabled" if task.enabled else "disabled"
        output = f" -> {task.output_path}" if task.output_path else ""
        lines.append(f"{task.name} [{state}] {task.task_type}: {description} {schedule_text}{output}")
    return lines


def run_launchd_scheduler(name: str | None = None) -> None:
    results = run_scheduler(name) if name is not None else run_scheduler()
    for result in results:
        print(f"Ran {result.task_name}: {result.output_path}")


def _run_launchctl(action: str, plist_path: Path) -> None:
    uid = getattr(os, "getuid", lambda: 0)()
    completed = subprocess.run(
        ["launchctl", action, f"gui/{uid}", str(plist_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"launchctl {action} failed with exit code {completed.returncode}")


def install_launchd_agent(*, plist_path: Path | None = None) -> Path:
    path = plist_path or get_launch_agent_plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_launch_agent_plist(), encoding="utf-8")
    _run_launchctl("bootstrap", path)
    return path


def uninstall_launchd_agent(*, plist_path: Path | None = None) -> Path:
    path = plist_path or get_launch_agent_plist_path()
    if path.exists():
        _run_launchctl("bootout", path)
        path.unlink()
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="apple-ecosystem-mcp schedule")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List configured scheduled tasks")
    run_parser = subparsers.add_parser("run", help="Run all enabled scheduled tasks or one named task")
    run_parser.add_argument("name", nargs="?", help="Optional scheduled task name to run")
    subparsers.add_parser("install", help="Install the launchd agent")
    subparsers.add_parser("uninstall", help="Remove the launchd agent")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(list(argv) if argv is not None else sys.argv[2:])

    if args.command == "list":
        for line in list_scheduled_tasks():
            print(line)
        return

    if args.command == "run":
        run_launchd_scheduler(args.name)
        return

    if args.command == "install":
        path = install_launchd_agent()
        print(f"Installed launchd agent at {path}")
        return

    if args.command == "uninstall":
        path = uninstall_launchd_agent()
        print(f"Removed launchd agent at {path}")
        return
