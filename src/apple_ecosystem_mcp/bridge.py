from __future__ import annotations

import logging
import os
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Iterable

_lock = threading.Lock()

_logger = logging.getLogger("apple_ecosystem_mcp.bridge")
_logger.propagate = False
if not _logger.handlers:
    # DEBUG-only file logging; never emit sensitive stderr to stdout/stderr.
    #
    # IMPORTANT: In Claude Desktop / MCPB bundles, the process CWD may be a
    # read-only directory (sometimes even "/"). Logging must never prevent the
    # server from starting.
    candidates: list[Path] = []

    env_path = os.environ.get("APPLE_ECOSYSTEM_MCP_LOG_PATH")
    if env_path:
        candidates.append(Path(env_path))

    if os.name == "posix":
        candidates.append(Path.home() / "Library" / "Logs" / "apple-ecosystem-mcp" / "debug.log")
        candidates.append(Path.home() / ".cache" / "apple-ecosystem-mcp" / "debug.log")
    candidates.append(Path(tempfile.gettempdir()) / "apple-ecosystem-mcp-debug.log")

    handler: logging.Handler | None = None
    for log_path in candidates:
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            handler = logging.FileHandler(log_path)
            break
        except OSError:
            continue

    if handler is None:
        handler = logging.NullHandler()

    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    _logger.addHandler(handler)
_logger.setLevel(logging.DEBUG)


def as_quote(value: str) -> str:
    """Escape a Python string for embedding inside an AppleScript string literal.

    This is only for rare cases where argv passing cannot be used. The returned
    value is intended to be placed between the *outer* double-quotes of an
    AppleScript string literal:

        set x to "{as_quote(value)}"

    It escapes backslashes and replaces embedded quotes with:
        " → " & quote & "
    """

    # Backslash escaping is primarily for correctness when the AppleScript source
    # is embedded in Python strings and to match the plan's explicit contract.
    return value.replace("\\", "\\\\").replace('"', '" & quote & "')


def _cmd(script: str, args: Iterable[str]) -> list[str]:
    return ["/usr/bin/osascript", "-e", script, "--", *list(args)]


def run_applescript(script: str, *args: str) -> str:
    """Run AppleScript via osascript using argv passing; raise RuntimeError on failure."""
    with _lock:
        try:
            result = subprocess.run(
                _cmd(script, args),
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        except subprocess.TimeoutExpired as e:
            _logger.debug("osascript timeout: %s", e)
            raise RuntimeError("AppleScript timed out") from e

    if result.returncode != 0:
        # Do not surface stderr to callers; it may include user data (subjects, names, paths).
        _logger.debug("osascript failed (exit %s): %s", result.returncode, result.stderr)
        raise RuntimeError(f"AppleScript failed (exit {result.returncode})")

    return (result.stdout or "").strip()
