from __future__ import annotations

import importlib.metadata
import subprocess
from subprocess import CompletedProcess
from typing import Callable
from unittest.mock import Mock

import pytest


@pytest.fixture
def completed_process_factory() -> Callable[..., CompletedProcess[str]]:
    """Helper to build CompletedProcess(returncode=0, stdout='...', stderr='')."""

    def factory(*, returncode: int = 0, stdout: str = "", stderr: str = "") -> CompletedProcess[str]:
        return CompletedProcess(args=["osascript"], returncode=returncode, stdout=stdout, stderr=stderr)

    return factory


@pytest.fixture
def mock_osascript(monkeypatch) -> Callable[..., Mock]:
    """Mock subprocess.run to avoid real osascript calls."""

    def factory(*, stdout: str = "", stderr: str = "", returncode: int = 0) -> Mock:
        def run_side_effect(*args, **kwargs):
            return CompletedProcess(
                args=args[0],
                returncode=returncode,
                stdout=stdout,
                stderr=stderr,
            )

        run_mock = Mock(side_effect=run_side_effect)
        monkeypatch.setattr(subprocess, "run", run_mock)
        return run_mock

    return factory


@pytest.fixture
def timeout_error_factory(monkeypatch) -> Callable[[], Mock]:
    """Raise TimeoutExpired on subprocess.run."""

    def factory() -> Mock:
        def run_side_effect(*args, **kwargs):
            raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs.get("timeout", 30))

        run_mock = Mock(side_effect=run_side_effect)
        monkeypatch.setattr(subprocess, "run", run_mock)
        return run_mock

    return factory


@pytest.fixture
def mock_package_version(monkeypatch) -> Callable[[str], None]:
    """Patch importlib.metadata.version() for CLI tests."""

    def factory(value: str) -> None:
        monkeypatch.setattr(importlib.metadata, "version", lambda *_args, **_kwargs: value)

    return factory


@pytest.fixture
def mock_server_run(monkeypatch) -> Mock:
    """Patch apple_ecosystem_mcp.server.run() for CLI tests."""
    from apple_ecosystem_mcp import server

    run_mock = Mock()
    monkeypatch.setattr(server, "run", run_mock)
    return run_mock
