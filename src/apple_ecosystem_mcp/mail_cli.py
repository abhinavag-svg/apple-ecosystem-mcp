from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .mail_store import MailStoreUnavailable, inspect_mail_store, refresh_mail_snapshot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="apple-ecosystem-mcp mail")
    subparsers = parser.add_subparsers(dest="command", required=True)

    diagnostics = subparsers.add_parser("diagnostics", help="Inspect local Apple Mail metadata access")
    diagnostics.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    refresh = subparsers.add_parser(
        "refresh-snapshot",
        help="Create a temporary Mail metadata snapshot from Terminal",
    )
    refresh.add_argument("--ttl-seconds", type=int, default=900, help="Snapshot time-to-live in seconds")
    refresh.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    return parser


def _emit(payload: dict, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    for key in sorted(payload):
        print(f"{key}: {payload[key]}")


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(list(argv) if argv is not None else sys.argv[2:])

    if args.command == "diagnostics":
        _emit(inspect_mail_store(), as_json=args.json)
        return

    if args.command == "refresh-snapshot":
        try:
            payload = refresh_mail_snapshot(ttl_seconds=args.ttl_seconds)
        except MailStoreUnavailable as exc:
            payload = exc.to_dict()
            if exc.code == "mail_store_permission_denied":
                payload["next_step"] = (
                    "Grant Full Disk Access to Terminal, then rerun this command."
                )
                payload["settings_path"] = "System Settings > Privacy & Security > Full Disk Access"
            _emit(payload, as_json=args.json)
            raise SystemExit(1) from exc

        result = {
            "ok": True,
            "provider": "mail_store_snapshot",
            "source_path": payload["source_path"],
            "snapshot_db_path": payload["snapshot_db_path"],
            "created_at": payload["created_at"],
            "expires_at": payload["expires_at"],
            "ttl_seconds": payload["ttl_seconds"],
            "copied_files": payload["copied_files"],
        }
        _emit(result, as_json=args.json)
        return
