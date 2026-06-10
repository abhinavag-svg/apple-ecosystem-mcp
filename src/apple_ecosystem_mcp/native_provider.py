from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

HELPER_NAME = "apple-ecosystem-helper"


class NativeProviderUnavailable(RuntimeError):
    """Raised when the native helper is intentionally unavailable."""


class NativeProviderError(RuntimeError):
    """Raised when the native helper returns a structured failure."""

    def __init__(self, code: str, message: str, *, recoverable: bool = True) -> None:
        super().__init__(message)
        self.code = code
        self.recoverable = recoverable

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.code,
            "message": str(self),
            "recoverable": self.recoverable,
        }


def native_enabled() -> bool:
    value = os.environ.get("APPLE_ECOSYSTEM_MCP_PROVIDER", "native").strip().lower()
    if value in {"applescript", "legacy", "off", "0", "false"}:
        return False
    return os.environ.get("APPLE_ECOSYSTEM_MCP_NATIVE", "1").strip().lower() not in {
        "0",
        "false",
        "off",
        "no",
    }


def helper_path() -> Path:
    override = os.environ.get("APPLE_ECOSYSTEM_MCP_HELPER_PATH")
    if override:
        path = Path(override).expanduser()
        if path.exists():
            return path
        raise NativeProviderUnavailable("Native helper is not available")

    here = Path(__file__).resolve()
    candidates: list[Path] = []
    for parent in here.parents:
        candidates.extend(
            [
                parent / "bin" / HELPER_NAME,
                parent / "native" / "build" / HELPER_NAME,
                parent / ".build" / "release" / HELPER_NAME,
            ]
        )

    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return candidate

    raise NativeProviderUnavailable("Native helper is not available")


def call_native(
    domain: str,
    operation: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout: int = 15,
) -> Any:
    if not native_enabled():
        raise NativeProviderUnavailable("Native provider is disabled")

    command = [str(helper_path()), domain, operation]
    body = json.dumps(payload or {}, separators=(",", ":"))
    try:
        result = subprocess.run(
            command,
            input=body,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise NativeProviderError(
            "helper_timeout",
            "Native helper timed out",
            recoverable=True,
        ) from exc
    except OSError as exc:
        raise NativeProviderUnavailable("Native helper is not available") from exc

    if result.returncode == 127:
        raise NativeProviderUnavailable("Native helper is not available")

    try:
        envelope = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise NativeProviderError(
            "native_backend_error",
            "Native helper returned malformed JSON",
            recoverable=True,
        ) from exc

    if not isinstance(envelope, dict):
        raise NativeProviderError(
            "native_backend_error",
            "Native helper returned an invalid response",
            recoverable=True,
        )

    if envelope.get("ok") is True:
        return envelope.get("result")

    error = envelope.get("error")
    if isinstance(error, dict):
        raise NativeProviderError(
            str(error.get("code") or "native_backend_error"),
            str(error.get("message") or "Native backend failed"),
            recoverable=bool(error.get("recoverable", True)),
        )

    raise NativeProviderError(
        "native_backend_error",
        "Native backend failed",
        recoverable=True,
    )


def try_native(domain: str, operation: str, payload: dict[str, Any] | None = None, *, timeout: int = 15) -> Any:
    """Call native helper, but let callers fall back only when unavailable."""
    return call_native(domain, operation, payload, timeout=timeout)
