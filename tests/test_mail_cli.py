from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from apple_ecosystem_mcp import mail_cli
from apple_ecosystem_mcp.mail_store import MailStoreUnavailable


def test_mail_cli_diagnostics_json(monkeypatch, capsys):
    inspect_mock = Mock(return_value={"ok": True, "provider": "mail_store"})
    monkeypatch.setattr(mail_cli, "inspect_mail_store", inspect_mock)

    mail_cli.main(["diagnostics", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    inspect_mock.assert_called_once_with()


def test_mail_cli_refresh_snapshot_json(monkeypatch, capsys):
    refresh_mock = Mock(
        return_value={
            "source_path": "/src/Envelope Index",
            "snapshot_db_path": "/tmp/snapshot/Envelope Index",
            "created_at": 1.0,
            "expires_at": 901.0,
            "ttl_seconds": 900,
            "copied_files": ["Envelope Index"],
        }
    )
    monkeypatch.setattr(mail_cli, "refresh_mail_snapshot", refresh_mock)

    mail_cli.main(["refresh-snapshot", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["provider"] == "mail_store_snapshot"


def test_mail_cli_refresh_snapshot_permission_error(monkeypatch, capsys):
    refresh_mock = Mock(
        side_effect=MailStoreUnavailable("mail_store_permission_denied", "Denied")
    )
    monkeypatch.setattr(mail_cli, "refresh_mail_snapshot", refresh_mock)

    with pytest.raises(SystemExit, match="1"):
        mail_cli.main(["refresh-snapshot", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "mail_store_permission_denied"
    assert "Terminal" in payload["next_step"]


def test_main_dispatches_mail_subcommand(monkeypatch):
    mail_main_mock = Mock()
    check_mock = Mock()
    run_mock = Mock()
    monkeypatch.setattr("apple_ecosystem_mcp.main.mail_cli.main", mail_main_mock)
    monkeypatch.setattr("apple_ecosystem_mcp.main.check_permissions", check_mock)
    monkeypatch.setattr("apple_ecosystem_mcp.main.run", run_mock)
    monkeypatch.setattr(mail_cli.sys, "argv", ["apple-ecosystem-mcp", "mail", "diagnostics"])

    from apple_ecosystem_mcp.main import main

    main()

    mail_main_mock.assert_called_once_with(["diagnostics"])
    check_mock.assert_not_called()
    run_mock.assert_not_called()
