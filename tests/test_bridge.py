from __future__ import annotations

import subprocess
import threading
import time
from subprocess import CompletedProcess
from unittest.mock import Mock

import pytest

from apple_ecosystem_mcp.bridge import as_quote, run_applescript


def test_run_applescript_returns_stdout(mock_osascript):
    mock_osascript(stdout="ok\n", stderr="", returncode=0)
    out = run_applescript("return 1", "a", "b")
    assert out == "ok"


def test_run_applescript_nonzero_exit_raises_without_stderr(mock_osascript):
    mock_osascript(stdout="", stderr="sensitive subject", returncode=7)
    with pytest.raises(RuntimeError) as e:
        run_applescript("return 1", "x")
    assert str(e.value) == "AppleScript failed (exit 7)"
    assert "sensitive" not in str(e.value)


def test_run_applescript_timeout(timeout_error_factory):
    timeout_error_factory()
    with pytest.raises(RuntimeError) as e:
        run_applescript("return 1")
    assert str(e.value) == "AppleScript timed out"


def test_run_applescript_calls_osascript_with_argv(mock_osascript):
    run_mock = mock_osascript(stdout="ok\n", stderr="", returncode=0)
    script = "return 1"
    out = run_applescript(script, "a", "b")
    assert out == "ok"
    args0 = run_mock.call_args.args[0]
    assert args0 == ["osascript", "-e", script, "--", "a", "b"]
    assert run_mock.call_args.kwargs["capture_output"] is True
    assert run_mock.call_args.kwargs["text"] is True
    assert run_mock.call_args.kwargs["timeout"] == 60
    assert run_mock.call_args.kwargs["check"] is False


def test_run_applescript_lock_serializes_concurrent_calls(monkeypatch):
    started_first = threading.Event()
    release_first = threading.Event()
    second_entered_subprocess = threading.Event()
    call_count = {"n": 0}

    def run_side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            started_first.set()
            release_first.wait(timeout=2)
            return CompletedProcess(args=args[0], returncode=0, stdout="first\n", stderr="")
        second_entered_subprocess.set()
        return CompletedProcess(args=args[0], returncode=0, stdout="second\n", stderr="")

    run_mock = Mock(side_effect=run_side_effect)
    monkeypatch.setattr(subprocess, "run", run_mock)

    results: list[str] = []

    def call(label: str) -> None:
        results.append(run_applescript(f"return '{label}'"))

    t1 = threading.Thread(target=call, args=("first",), daemon=True)
    t2 = threading.Thread(target=call, args=("second",), daemon=True)

    t1.start()
    assert started_first.wait(timeout=2)
    t2.start()

    # While the first call is blocked inside subprocess.run, the second call must
    # not reach subprocess.run because the module-level lock is held.
    time.sleep(0.05)
    assert second_entered_subprocess.is_set() is False

    release_first.set()
    t1.join(timeout=2)
    t2.join(timeout=2)

    assert second_entered_subprocess.is_set() is True
    assert results == ["first", "second"]


def test_as_quote_escapes_backslashes_and_quotes():
    expr = as_quote('a\\b"c')
    assert "\\\\" in expr
    assert '" & quote & "' in expr
