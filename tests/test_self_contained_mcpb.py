from __future__ import annotations

import json
import os
import select
import subprocess
import time
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BUNDLE_PATH = ROOT / "mcpb" / "apple-ecosystem-mcp.mcpb"


def _encode_message(payload: dict) -> bytes:
    return json.dumps(payload).encode("utf-8") + b"\n"


def _read_available(stream, *, timeout: float) -> bytes:
    fd = stream.fileno()
    deadline = time.monotonic() + timeout
    chunks: list[bytes] = []
    while time.monotonic() < deadline:
        remaining = max(0.01, deadline - time.monotonic())
        readable, _, _ = select.select([fd], [], [], remaining)
        if not readable:
            continue
        chunk = os.read(fd, 4096)
        if not chunk:
            break
        chunks.append(chunk)
        break
    return b"".join(chunks)


def _read_message(proc: subprocess.Popen[bytes], *, timeout: float = 20) -> dict:
    assert proc.stdout is not None
    deadline = time.monotonic() + timeout
    buffer = b""
    while time.monotonic() < deadline:
        chunk = _read_available(proc.stdout, timeout=max(0.01, deadline - time.monotonic()))
        if chunk:
            buffer += chunk
            while b"\n" in buffer:
                raw_line, buffer = buffer.split(b"\n", 1)
                line = raw_line.strip()
                if not line or not line.startswith(b"{"):
                    continue
                return json.loads(line.decode("utf-8"))
            continue
        if proc.poll() is not None:
            stderr = proc.stderr.read().decode("utf-8", errors="replace") if proc.stderr else ""
            raise AssertionError(f"packaged server exited before MCP response was received: {stderr}")
    raise AssertionError("timed out waiting for packaged server MCP response")


@pytest.mark.skipif(not BUNDLE_PATH.exists(), reason="self-contained MCPB has not been built")
def test_self_contained_mcpb_launches_over_stdio(tmp_path):
    install_root = tmp_path / "installed"
    with zipfile.ZipFile(BUNDLE_PATH) as bundle:
        bundle.extractall(install_root)

    manifest = json.loads((install_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["server"] == {
        "type": "binary",
        "entry_point": "bin/apple-ecosystem-mcp",
        "mcp_config": {
            "command": "${__dirname}/bin/apple-ecosystem-mcp",
            "args": [],
            "env": {},
        },
    }

    executable = install_root / "bin" / "apple-ecosystem-mcp"
    helper = install_root / "bin" / "apple-ecosystem-helper"
    assert executable.exists()
    assert helper.exists()
    executable.chmod(executable.stat().st_mode | 0o755)
    helper.chmod(helper.stat().st_mode | 0o755)

    proc = subprocess.Popen(
        [str(executable)],
        cwd=install_root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert proc.stdin is not None
        proc.stdin.write(
            _encode_message(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "pytest", "version": "0"},
                    },
                }
            )
        )
        proc.stdin.flush()
        initialize = _read_message(proc)
        assert initialize["id"] == 1

        proc.stdin.write(_encode_message({"jsonrpc": "2.0", "method": "notifications/initialized"}))
        proc.stdin.write(_encode_message({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}))
        proc.stdin.flush()
        tools = _read_message(proc)
        assert tools["id"] == 2
        tool_names = {tool["name"] for tool in tools["result"]["tools"]}
        assert "apple_inventory" in tool_names
    finally:
        proc.terminate()
        proc.wait(timeout=5)
