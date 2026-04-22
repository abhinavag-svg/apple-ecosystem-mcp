from __future__ import annotations

import os
from subprocess import CompletedProcess

import pytest

from apple_ecosystem_mcp.permissions import check_permissions


@pytest.mark.parametrize(
    ("denied_index", "name"),
    [
        (0, "Automation → Mail"),
        (1, "Automation → Calendar"),
        (2, "Automation → Contacts"),
        (3, "Automation → Reminders"),
    ],
)
def test_check_permissions_detects_automation_denial(monkeypatch, capsys, denied_index: int, name: str):
    results: list[CompletedProcess[str]] = []
    for i in range(4):
        if i == denied_index:
            results.append(
                CompletedProcess(
                    args=["osascript"],
                    returncode=1,
                    stdout="",
                    stderr="Execution error: -1743",
                )
            )
        else:
            results.append(CompletedProcess(args=["osascript"], returncode=0, stdout="ok", stderr=""))

    it = iter(results)
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: next(it))
    monkeypatch.setattr(os, "listdir", lambda *_args, **_kwargs: [])

    check_permissions()
    out = capsys.readouterr().out
    assert f"⚠ Missing: {name}" in out
    assert "System Settings > Privacy & Security > Automation" in out


def test_check_permissions_detects_apple_events_denial_text(monkeypatch, capsys):
    # First probe denied via message, others succeed.
    responses = [
        CompletedProcess(args=["osascript"], returncode=1, stdout="", stderr="Not allowed to send Apple events"),
        CompletedProcess(args=["osascript"], returncode=0, stdout="ok", stderr=""),
        CompletedProcess(args=["osascript"], returncode=0, stdout="ok", stderr=""),
        CompletedProcess(args=["osascript"], returncode=0, stdout="ok", stderr=""),
    ]
    it = iter(responses)
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: next(it))
    monkeypatch.setattr(os, "listdir", lambda *_args, **_kwargs: [])

    check_permissions()
    out = capsys.readouterr().out
    assert "⚠ Missing: Automation → Mail" in out


def test_check_permissions_detects_full_disk_access_denial(monkeypatch, capsys):
    # All automation probes succeed; Full Disk Access fails via PermissionError.
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: CompletedProcess(args=["osascript"], returncode=0, stdout="ok", stderr=""),
    )
    monkeypatch.setattr(os, "listdir", lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError()))

    check_permissions()
    out = capsys.readouterr().out
    assert "⚠ Missing: Full Disk Access" in out
    assert "System Settings > Privacy & Security > Full Disk Access" in out


def test_check_permissions_does_not_abort_on_unexpected_errors(monkeypatch):
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(os, "listdir", lambda *_args, **_kwargs: (_ for _ in ()).throw(FileNotFoundError()))
    check_permissions()
