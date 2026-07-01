from __future__ import annotations

import os
import stat
import subprocess

import pytest

from apple_ecosystem_mcp import native_provider


def _fake_helper(tmp_path, body: str):
    path = tmp_path / "helper.py"
    path.write_text(body)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_call_native_success(monkeypatch, tmp_path):
    helper = _fake_helper(
        tmp_path,
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "payload=json.load(sys.stdin)\n"
        "print(json.dumps({'ok': True, 'result': {'echo': payload['value']}}))\n",
    )
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_PROVIDER", "native")
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_HELPER_PATH", str(helper))

    assert native_provider.call_native("calendar", "health", {"value": "ok"}) == {"echo": "ok"}


def test_call_native_error_envelope(monkeypatch, tmp_path):
    helper = _fake_helper(
        tmp_path,
        "#!/usr/bin/env python3\n"
        "import json\n"
        "print(json.dumps({'ok': False, 'error': {'code': 'permission_denied', 'message': 'Nope', 'recoverable': True}}))\n",
    )
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_PROVIDER", "native")
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_HELPER_PATH", str(helper))

    with pytest.raises(native_provider.NativeProviderError) as exc:
        native_provider.call_native("contacts", "search")
    assert exc.value.code == "permission_denied"
    assert exc.value.recoverable is True


def test_call_native_malformed_json(monkeypatch, tmp_path):
    helper = _fake_helper(tmp_path, "#!/usr/bin/env python3\nprint('not-json')\n")
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_PROVIDER", "native")
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_HELPER_PATH", str(helper))

    with pytest.raises(native_provider.NativeProviderError) as exc:
        native_provider.call_native("contacts", "search")
    assert exc.value.code == "native_backend_error"


def test_call_native_timeout(monkeypatch):
    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["helper"], timeout=1)

    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_PROVIDER", "native")
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_HELPER_PATH", "/bin/echo")
    monkeypatch.setattr(native_provider.subprocess, "run", timeout)

    with pytest.raises(native_provider.NativeProviderError) as exc:
        native_provider.call_native("contacts", "search", timeout=1)
    assert exc.value.code == "helper_timeout"


def test_call_native_disabled(monkeypatch):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_PROVIDER", "applescript")
    with pytest.raises(native_provider.NativeProviderUnavailable):
        native_provider.call_native("calendar", "health")


def test_helper_path_missing_override(monkeypatch, tmp_path):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_PROVIDER", "native")
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_HELPER_PATH", str(tmp_path / "missing"))

    with pytest.raises(native_provider.NativeProviderUnavailable):
        native_provider.helper_path()


def test_helper_path_checks_frozen_executable_directory(monkeypatch, tmp_path):
    helper = tmp_path / native_provider.HELPER_NAME
    helper.write_text("#!/bin/sh\n", encoding="utf-8")
    helper.chmod(helper.stat().st_mode | stat.S_IXUSR)

    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_PROVIDER", "native")
    monkeypatch.delenv("APPLE_ECOSYSTEM_MCP_HELPER_PATH", raising=False)
    monkeypatch.setattr(native_provider.sys, "frozen", True, raising=False)
    monkeypatch.setattr(native_provider.sys, "executable", str(tmp_path / "apple-ecosystem-mcp"))

    assert native_provider.helper_path() == helper
