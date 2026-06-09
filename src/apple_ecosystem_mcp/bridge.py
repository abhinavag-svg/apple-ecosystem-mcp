from __future__ import annotations

import functools
import copy
import logging
import os
import reprlib
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterable

_lock = threading.Lock()  # Serializes AppleScript calls (not reentrant)
_cache_lock = threading.Lock()  # Protects cache dict
_cache: dict[str, tuple[float, Any]] = {}

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


def run_applescript(script: str, *args: str, timeout: int = 60) -> str:
    """Run AppleScript via osascript using argv passing; raise RuntimeError on failure."""
    with _lock:
        try:
            result = subprocess.run(
                _cmd(script, args),
                capture_output=True,
                text=True,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
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


def clear_inventory_cache() -> None:
    """Clear all cached inventory results. Used in tests."""
    with _cache_lock:
        _cache.clear()


def _cache_key(cache_key: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
    parts = [cache_key]
    if args:
        parts.append(reprlib.repr(args))
    if kwargs:
        parts.append(reprlib.repr(sorted(kwargs.items())))
    return "|".join(parts)


def cache_inventory(cache_key: str, ttl: int = 30) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to cache inventory results for a given TTL (seconds).

    Thread-safe: uses a separate cache lock (not the AppleScript lock).
    Useful for expensive operations like mail_list_mailboxes(), reminders_lists(), etc.

    Args:
        cache_key: Unique key for this cached inventory (e.g., "mail_mailboxes")
        ttl: Cache TTL in seconds (default 30)

    Returns:
        Decorator that wraps the function with caching
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            now = time.time()
            key = _cache_key(cache_key, args, kwargs)
            with _cache_lock:
                if key in _cache:
                    cached_time, cached_value = _cache[key]
                    if now - cached_time < ttl:
                        return copy.deepcopy(cached_value)
            result = func(*args, **kwargs)
            with _cache_lock:
                _cache[key] = (now, copy.deepcopy(result))
            return result
        return wrapper
    return decorator
