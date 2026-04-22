from __future__ import annotations

import os
import subprocess
from pathlib import Path

ICLOUD_ROOT = Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"

_AUTOMATION_SETTINGS = "System Settings > Privacy & Security > Automation"
_FDA_SETTINGS = "System Settings > Privacy & Security > Full Disk Access"
_GRANT_TEXT = "Grant access to Terminal (or apple-ecosystem-mcp after install)"


def _run_applescript_probe(script: str) -> tuple[int, str]:
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    return result.returncode, (result.stderr or "")


def _is_tcc_denied(returncode: int, stderr: str) -> bool:
    # TCC denial is typically exit code 1 with either an -1743 error code
    # or the "not allowed to send Apple events" message.
    if returncode != 1:
        return False
    lowered = stderr.lower()
    return ("-1743" in stderr) or ("not allowed to send apple events" in lowered)


def _probe_mail() -> bool:
    """Probe Mail automation permission."""
    code, stderr = _run_applescript_probe('tell application "Mail" to return name')
    return not _is_tcc_denied(code, stderr)


def _probe_calendar() -> bool:
    """Probe Calendar automation permission."""
    code, stderr = _run_applescript_probe('tell application "Calendar" to return name')
    return not _is_tcc_denied(code, stderr)


def _probe_contacts() -> bool:
    """Probe Contacts automation permission."""
    code, stderr = _run_applescript_probe('tell application "Contacts" to return name')
    return not _is_tcc_denied(code, stderr)


def _probe_reminders() -> bool:
    """Probe Reminders automation permission."""
    code, stderr = _run_applescript_probe('tell application "Reminders" to return name')
    return not _is_tcc_denied(code, stderr)


def _probe_full_disk_access() -> bool:
    """Probe Full Disk Access via iCloud Drive root."""
    try:
        os.listdir(ICLOUD_ROOT)
        return True
    except PermissionError:
        return False
    except FileNotFoundError:
        # iCloud Drive not enabled or the folder isn't present.
        return True


def check_permissions() -> None:
    """Probe common macOS TCC permissions and print actionable guidance if missing.

    This must never block server startup; missing permissions will surface later
    as tool errors when the user invokes functionality.
    """
    missing: list[tuple[str, str]] = []

    try:
        if not _probe_mail():
            missing.append(("Automation → Mail", _AUTOMATION_SETTINGS))
    except Exception:
        pass
    try:
        if not _probe_calendar():
            missing.append(("Automation → Calendar", _AUTOMATION_SETTINGS))
    except Exception:
        pass
    try:
        if not _probe_contacts():
            missing.append(("Automation → Contacts", _AUTOMATION_SETTINGS))
    except Exception:
        pass
    try:
        if not _probe_reminders():
            missing.append(("Automation → Reminders", _AUTOMATION_SETTINGS))
    except Exception:
        pass

    try:
        if not _probe_full_disk_access():
            missing.append(("Full Disk Access", _FDA_SETTINGS))
    except Exception:
        pass

    for name, settings_path in missing:
        print(f"⚠ Missing: {name} → {settings_path} → {_GRANT_TEXT}")
