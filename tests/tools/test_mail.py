from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from apple_ecosystem_mcp import mail_service
from apple_ecosystem_mcp.mail_store import MailStoreUnavailable
from apple_ecosystem_mcp.prompt_contract import MAIL_RECENT_CONTRACT, MAIL_SEARCH_CONTRACT
from apple_ecosystem_mcp.tools import mail


@pytest.fixture(autouse=True)
def _force_applescript_mail_provider(monkeypatch):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER", "applescript")


def _inspect_tools(mcp):
    return {tool.name: tool for tool in mcp.local_provider._components.values()}


# ---------------------------------------------------------------------------
# Tool registration / annotations
# ---------------------------------------------------------------------------


def test_mail_tools_registered():
    from apple_ecosystem_mcp import server

    tools = _inspect_tools(server.mcp)
    for name in [
        "mail_search",
        "mail_recent",
        "mail_diagnostics",
        "mail_access_setup",
        "refresh_mail_snapshot",
        "mail_get_thread",
        "mail_open_message",
        "mail_send",
        "mail_create_draft",
        "mail_list_mailboxes",
        "mail_move_message",
        "mail_flag_message",
        "mail_delete",
    ]:
        assert name in tools


def test_readonly_annotations():
    from apple_ecosystem_mcp import server

    tools = _inspect_tools(server.mcp)
    assert tools["mail_search"].annotations.readOnlyHint is True
    assert tools["mail_recent"].annotations.readOnlyHint is True
    assert tools["mail_diagnostics"].annotations.readOnlyHint is True
    assert tools["mail_get_thread"].annotations.readOnlyHint is True
    assert tools["mail_list_mailboxes"].annotations.readOnlyHint is True


def test_mail_tool_titles_and_descriptions():
    from apple_ecosystem_mcp import server

    tools = _inspect_tools(server.mcp)
    assert tools["mail_search"].annotations.title == MAIL_SEARCH_CONTRACT.title
    assert tools["mail_recent"].annotations.title == MAIL_RECENT_CONTRACT.title
    assert tools["mail_search"].description == MAIL_SEARCH_CONTRACT.description
    assert tools["mail_recent"].description == MAIL_RECENT_CONTRACT.description


def test_mail_delete_destructive_annotation():
    from apple_ecosystem_mcp import server

    tools = _inspect_tools(server.mcp)
    assert tools["mail_delete"].annotations.destructiveHint is True


def test_mail_move_message_is_not_marked_destructive():
    from apple_ecosystem_mcp import server

    tools = _inspect_tools(server.mcp)
    assert not tools["mail_move_message"].annotations.destructiveHint


def test_mail_open_message_is_not_marked_destructive():
    from apple_ecosystem_mcp import server

    tools = _inspect_tools(server.mcp)
    assert not tools["mail_open_message"].annotations.destructiveHint


# ---------------------------------------------------------------------------
# mail_list_mailboxes
# ---------------------------------------------------------------------------


def test_mail_list_mailboxes_returns_shape(monkeypatch):
    payload = [
        {"name": "INBOX", "id": "1A", "account_name": "iCloud", "path": "INBOX", "writable": True},
        {"name": "Sent", "id": "2B", "account_name": "iCloud", "path": "Sent", "writable": False},
    ]
    monkeypatch.setattr(mail, "store_list_mailboxes", Mock(side_effect=MailStoreUnavailable("x", "x")))
    monkeypatch.setattr(mail, "run_applescript", Mock(return_value=json.dumps(payload)))
    result = mail.mail_list_mailboxes()
    assert len(result) == 2
    for mb in result:
        assert {"id", "name", "kind", "account_name", "path", "writable", "default_candidate"} <= set(mb.keys())
        assert mb["kind"] == "mailbox"
    assert result[0]["default_candidate"] is True
    assert result[1]["default_candidate"] is False
    assert result[0]["writable"] is True
    assert result[1]["writable"] is False


def test_mail_list_mailboxes_handles_empty(monkeypatch):
    monkeypatch.setattr(mail, "store_list_mailboxes", Mock(side_effect=MailStoreUnavailable("x", "x")))
    monkeypatch.setattr(mail, "run_applescript", Mock(return_value=""))
    assert mail.mail_list_mailboxes() == []


def test_mail_list_mailboxes_rejects_non_list(monkeypatch):
    monkeypatch.setattr(mail, "store_list_mailboxes", Mock(side_effect=MailStoreUnavailable("x", "x")))
    monkeypatch.setattr(mail, "run_applescript", Mock(return_value='{"oops": true}'))
    with pytest.raises(RuntimeError, match="payload"):
        mail.mail_list_mailboxes()


def test_mail_list_mailboxes_prefers_store_inventory(monkeypatch):
    run_mock = Mock(return_value="[]")
    monkeypatch.setattr(mail, "run_applescript", run_mock)
    monkeypatch.setattr(
        mail,
        "store_list_mailboxes",
        Mock(
            return_value=[
                {
                    "mailbox_id": "imap://icloud/INBOX",
                    "mailbox_url": "imap://icloud/INBOX",
                    "mailbox_path": "INBOX",
                    "account_token": "imap://icloud",
                    "account_name": "iCloud",
                },
                {
                    "mailbox_id": "ews://hotmail/Inbox",
                    "mailbox_url": "ews://hotmail/Inbox",
                    "mailbox_path": "Inbox",
                    "account_token": "ews://hotmail",
                    "account_name": "Abhinav Hotmail",
                },
            ]
        ),
    )

    result = mail.mail_list_mailboxes()

    assert [item["account_name"] for item in result] == ["iCloud", "Abhinav Hotmail"]
    assert [item["id"] for item in result] == ["imap://icloud/INBOX", "ews://hotmail/Inbox"]
    assert all(item["provider"] == "mail_store" for item in result)
    assert all(item["writable"] is None for item in result)
    run_mock.assert_not_called()


# ---------------------------------------------------------------------------
# mail_search / mail_recent wrappers
# ---------------------------------------------------------------------------


def test_mail_search_delegates_to_service(monkeypatch):
    search_mock = Mock(return_value=[{"id": "<msg@test>"}])
    monkeypatch.setattr(mail, "service_search_mail", search_mock)

    result = mail.mail_search(
        "invoice",
        mailbox_id="mb-7",
        limit=10,
        since="2026-04-01T00:00:00",
        before="2026-05-01T00:00:00",
        search_fields=["subject", "sender"],
        filters={"account_name": "iCloud"},
    )

    assert result[0]["id"] == "<msg@test>"
    assert result[0]["open_url"] == "message://%3Cmsg%40test%3E"
    assert result[0]["next_action"]["tool"] == "mail_get_thread"
    kwargs = search_mock.call_args.kwargs
    assert kwargs["mailbox_id"] == "mb-7"
    assert kwargs["limit"] == 10
    assert kwargs["since"] == "2026-04-01T00:00:00"
    assert kwargs["before"] == "2026-05-01T00:00:00"
    assert kwargs["search_fields"] == ["subject", "sender"]
    assert kwargs["filters"] == {"account_name": "iCloud"}
    assert kwargs["mailbox_inventory_fn"] is mail.mail_list_mailboxes


def test_mail_search_coerces_stringified_llm_arguments(monkeypatch):
    search_mock = Mock(return_value=[{"id": "<msg@test>"}])
    monkeypatch.setattr(mail, "service_search_mail", search_mock)

    result = mail.mail_search(
        "linkedin",
        limit="15",
        since="2026-06-19T08:00:00",
        search_fields='["from"]',
        filters='{"account_name": "iCloud"}',
    )

    assert result[0]["id"] == "<msg@test>"
    assert result[0]["open_action"]["type"] == "open_url"
    kwargs = search_mock.call_args.kwargs
    assert kwargs["limit"] == 15
    assert kwargs["since"] == "2026-06-19T08:00:00"
    assert kwargs["search_fields"] == ["from"]
    assert kwargs["filters"] == {"account_name": "iCloud"}


def test_mail_recent_delegates_to_service(monkeypatch):
    recent_mock = Mock(return_value=[{"id": "<recent@test>"}])
    monkeypatch.setattr(mail, "service_recent_mail", recent_mock)

    result = mail.mail_recent(
        limit=5,
        since="2026-06-10T22:00:00",
        before="2026-06-11T12:00:00",
        filters={"unread": True, "account_name": "iCloud"},
    )

    assert result[0]["id"] == "<recent@test>"
    assert result[0]["open_url"] == "message://%3Crecent%40test%3E"
    assert result[0]["next_action"]["tool"] == "mail_get_thread"
    kwargs = recent_mock.call_args.kwargs
    assert kwargs["limit"] == 5
    assert kwargs["since"] == "2026-06-10T22:00:00"
    assert kwargs["before"] == "2026-06-11T12:00:00"
    assert kwargs["filters"] == {"unread": True, "account_name": "iCloud"}
    assert kwargs["mailbox_inventory_fn"] is mail.mail_list_mailboxes


def test_mail_recent_coerces_stringified_filters(monkeypatch):
    recent_mock = Mock(return_value=[{"id": "<recent@test>"}])
    monkeypatch.setattr(mail, "service_recent_mail", recent_mock)

    result = mail.mail_recent(
        limit="10",
        since="2026-06-20T00:00:00",
        filters='{"unread": true}',
    )

    assert result[0]["id"] == "<recent@test>"
    assert result[0]["open_action"]["label"] == "Open in Mail"
    kwargs = recent_mock.call_args.kwargs
    assert kwargs["limit"] == 10
    assert kwargs["filters"] == {"unread": True}


def test_mail_diagnostics_delegates_to_store_inspection(monkeypatch):
    inspect_mock = Mock(return_value={"ok": True, "provider": "mail_store"})
    monkeypatch.setattr(mail, "inspect_mail_store", inspect_mock)

    result = mail.mail_diagnostics()

    assert result == {"ok": True, "provider": "mail_store"}
    inspect_mock.assert_called_once_with()


def test_mail_diagnostics_adds_next_action_when_unavailable(monkeypatch):
    inspect_mock = Mock(return_value={"ok": False, "error": "mail_store_permission_denied"})
    monkeypatch.setattr(mail, "inspect_mail_store", inspect_mock)

    result = mail.mail_diagnostics()

    assert result["next_action"]["tool"] == "mail_access_setup"


def test_mail_access_setup_reports_modes_without_opening_settings(monkeypatch):
    inspect_mock = Mock(return_value={"ok": False, "error": "mail_store_permission_denied"})
    open_mock = Mock()
    monkeypatch.setattr(mail, "inspect_mail_store", inspect_mock)
    monkeypatch.setattr(mail.subprocess, "run", open_mock)

    result = mail.mail_access_setup()

    assert result["local_store_access"] == "unavailable"
    assert result["recommended_default"] == "applescript_first_auto"
    assert [mode["mode"] for mode in result["modes"]] == ["auto", "applescript", "local"]
    assert result["settings_path"] == "System Settings > Privacy & Security > Full Disk Access"
    assert result["open_url"] == "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"
    assert result["next_action"]["type"] == "open_url"
    open_mock.assert_not_called()


def test_mail_access_setup_can_open_full_disk_access_settings(monkeypatch):
    monkeypatch.setattr(mail, "inspect_mail_store", Mock(return_value={"ok": True}))
    open_mock = Mock()
    monkeypatch.setattr(mail.subprocess, "run", open_mock)

    result = mail.mail_access_setup(open_settings=True)

    assert result["local_store_access"] == "available"
    assert result["settings_opened"] is True
    open_mock.assert_called_once_with(
        ["open", "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"],
        check=True,
        timeout=5,
    )


def test_refresh_mail_snapshot_delegates_to_store_refresh(monkeypatch):
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
    monkeypatch.setattr(mail, "store_refresh_mail_snapshot", refresh_mock)

    result = mail.refresh_mail_snapshot(ttl_seconds=900)

    assert result["ok"] is True
    assert result["provider"] == "mail_store_snapshot"
    assert result["snapshot_db_path"] == "/tmp/snapshot/Envelope Index"
    assert result["next_action"]["tool"] == "mail_recent"
    refresh_mock.assert_called_once_with(ttl_seconds=900)


def test_refresh_mail_snapshot_returns_structured_permission_error(monkeypatch):
    refresh_mock = Mock(
        side_effect=MailStoreUnavailable("mail_store_permission_denied", "Denied")
    )
    monkeypatch.setattr(mail, "store_refresh_mail_snapshot", refresh_mock)

    result = mail.refresh_mail_snapshot(ttl_seconds=900)

    assert result["error"] == "mail_store_permission_denied"
    assert "refresh-snapshot" in result["next_step"]
    assert "Full Disk Access" in result["settings_path"]
    assert result["open_url"] == "x-apple.systempreferences:com.apple.preference.security?Privacy_AllFiles"
    assert result["next_action"]["type"] == "terminal_command"


def test_mail_search_script_contract_smoke():
    assert "set preview to \"\"" in mail_service._SEARCH_SCRIPT
    assert "set preview to text 1 thru 200 of bodyText" not in mail_service._SEARCH_SCRIPT
    assert "if scanLim > 250 then set scanLim to 250" in mail_service._SEARCH_SCRIPT
    assert "if scanLim > 500 then set scanLim to 500" in mail_service._SEARCH_SCRIPT
    assert "if recentMode or unreadStr is not \"\"" in mail_service._SEARCH_SCRIPT
    assert "else if searchSubject and my containsCI(subj, qry) then" in mail_service._SEARCH_SCRIPT
    assert 'mbName is "INBOX"' in mail_service._SEARCH_SCRIPT
    assert "repeat with idx_ from 1 to scanLim" in mail_service._SEARCH_SCRIPT
    assert "exit repeat" in mail_service._SEARCH_SCRIPT


def test_mail_move_accepts_rfc_id(monkeypatch):
    run_mock = Mock(
        side_effect=[
            json.dumps(
                [
                    {
                        "name": "Archive",
                        "id": "mb-archive",
                        "account_name": "iCloud",
                        "path": "Archive",
                        "writable": True,
                    }
                ]
            ),
            json.dumps({"success": True}),
        ]
    )
    monkeypatch.setattr(mail, "run_applescript", run_mock)

    rfc_id = "<msg-12345@example.com>"
    result = mail.mail_move_message(rfc_id, "mb-archive")
    assert result["success"] is True
    assert run_mock.call_args.args[1:] == (rfc_id, "mb-archive")


def test_mail_flag_accepts_rfc_id(monkeypatch):
    run_mock = Mock(return_value=json.dumps({"success": True}))
    monkeypatch.setattr(mail, "run_applescript", run_mock)

    rfc_id = "<msg-12345@example.com>"
    result = mail.mail_flag_message(rfc_id, True)
    assert result["success"] is True
    assert run_mock.call_args.args[1:] == (rfc_id, "1")


def test_mail_delete_accepts_rfc_id(monkeypatch):
    run_mock = Mock(return_value=json.dumps({"success": True}))
    monkeypatch.setattr(mail, "run_applescript", run_mock)

    rfc_id = "<msg-12345@example.com>"
    result = mail.mail_delete(rfc_id, confirm=True)
    assert result["success"] is True
    assert run_mock.call_args.args[1:] == (rfc_id,)


# ---------------------------------------------------------------------------
# mail_get_thread
# ---------------------------------------------------------------------------


def test_mail_get_thread_plain_text_body(monkeypatch):
    payload = {
        "id": "<msg-1@test>",
        "internal_id": "101",
        "subject": "hi",
        "sender": "a@b.com",
        "date": "2026-04-01T10:00:00",
        "body": "hello world",
        "mailbox_id": "mb-1",
        "account_name": "iCloud",
        "attachments": [],
    }
    monkeypatch.setattr(
        mail,
        "_thread_scope_from_store",
        Mock(
            return_value={
                "id": "<msg-1@test>",
                "internal_id": "101",
                "mailbox_id": "imap://icloud/INBOX",
                "mailbox_path": "INBOX",
                "account_name": "iCloud",
            }
        ),
    )
    monkeypatch.setattr(mail, "run_applescript", Mock(return_value=json.dumps(payload)))
    result = mail.mail_get_thread("<msg-1@test>")
    assert result["id"] == "<msg-1@test>"
    assert result["body"] == "hello world"
    assert result["mailbox_id"] == "mb-1"
    assert result["account_name"] == "iCloud"


def test_mail_get_thread_strips_html_and_base64(monkeypatch):
    # A realistic base64 blob mixes upper, lower, and digits — long runs of a
    # single character are treated as plain text and preserved.
    base64_blob = ("AbCd1234EfGh5678" * 40)  # 640 chars, mixed alphabet
    heavy = f"<html><body><p>Keep me</p>{base64_blob}</body></html>"
    payload = {
        "id": "<m@x>",
        "subject": "s",
        "sender": "a@b",
        "date": "2026-04-01T00:00:00",
        "mailbox_id": "mb",
        "account_name": "acct",
        "attachments": [],
        "body": heavy,
    }
    monkeypatch.setattr(mail, "_thread_scope_from_store", Mock(return_value=None))
    monkeypatch.setattr(mail, "run_applescript", Mock(return_value=json.dumps(payload)))
    result = mail.mail_get_thread("<m@x>")
    assert "<p>" not in result["body"]
    assert "<html>" not in result["body"]
    assert base64_blob not in result["body"]
    assert "Keep me" in result["body"]


def test_mail_get_thread_truncates_at_8000(monkeypatch):
    body = "x" * 12_000
    payload = {
        "id": "<m@x>",
        "subject": "s",
        "sender": "a@b",
        "date": "2026-04-01T00:00:00",
        "mailbox_id": "mb",
        "account_name": "acct",
        "attachments": [],
        "body": body,
    }
    monkeypatch.setattr(mail, "_thread_scope_from_store", Mock(return_value=None))
    monkeypatch.setattr(mail, "run_applescript", Mock(return_value=json.dumps(payload)))
    result = mail.mail_get_thread("<m@x>")
    assert "truncated" in result["body"]
    assert "4000 chars omitted" in result["body"]
    assert result["body"].startswith("x" * 100)


def test_mail_get_thread_include_body_false_omits_body(monkeypatch):
    payload = {
        "id": "<m@x>",
        "internal_id": "55",
        "subject": "s",
        "sender": "a@b",
        "date": "2026-04-01T00:00:00",
        "mailbox_id": "imap://icloud/INBOX",
        "mailbox_path": "INBOX",
        "account_name": "acct",
        "attachments": [],
    }
    monkeypatch.setattr(mail, "_thread_scope_from_store", Mock(return_value=payload))
    run_mock = Mock(return_value=json.dumps(payload))
    monkeypatch.setattr(mail, "run_applescript", run_mock)
    result = mail.mail_get_thread("<m@x>", include_body=False)
    assert "body" not in result
    assert result["attachments"] == []
    run_mock.assert_not_called()


def test_mail_get_thread_attachment_metadata(monkeypatch):
    payload = {
        "id": "<m@x>",
        "subject": "s",
        "sender": "a@b",
        "date": "2026-04-01T00:00:00",
        "mailbox_id": "mb",
        "account_name": "acct",
        "attachments": [
            {"name": "report.pdf", "size_bytes": 1024, "mime_type": "application/pdf"},
        ],
        "body": "x",
    }
    monkeypatch.setattr(mail, "_thread_scope_from_store", Mock(return_value=None))
    monkeypatch.setattr(mail, "run_applescript", Mock(return_value=json.dumps(payload)))
    result = mail.mail_get_thread("<m@x>")
    assert result["attachments"][0]["name"] == "report.pdf"
    assert result["attachments"][0]["size_bytes"] == 1024
    assert result["attachments"][0]["mime_type"] == "application/pdf"


def test_mail_get_thread_rejects_non_dict(monkeypatch):
    monkeypatch.setattr(mail, "_thread_scope_from_store", Mock(return_value=None))
    monkeypatch.setattr(mail, "run_applescript", Mock(return_value="[1,2,3]"))
    with pytest.raises(RuntimeError, match="payload"):
        mail.mail_get_thread("<m@x>")


def test_mail_get_thread_uses_safe_mailbox_identifier_helper():
    assert "set mbId to my mailboxIdentifier(mb)" in mail._GET_THREAD_SCRIPT
    assert "on mailboxIdentifier(mb)" in mail._GET_THREAD_SCRIPT


def test_mail_get_thread_passes_scoped_store_hints_to_applescript(monkeypatch):
    scoped = {
        "id": "<m@x>",
        "internal_id": "77",
        "mail_object_id": "177",
        "subject": "s",
        "sender": "a@b",
        "date": "2026-04-01T00:00:00",
        "mailbox_id": "imap://icloud/INBOX",
        "mailbox_path": "INBOX",
        "account_name": "iCloud",
        "attachments": [],
    }
    payload = dict(scoped)
    payload["body"] = "hello"
    monkeypatch.setattr(mail, "_thread_scope_from_store", Mock(return_value=scoped))
    run_mock = Mock(return_value=json.dumps(payload))
    monkeypatch.setattr(mail, "run_applescript", run_mock)

    result = mail.mail_get_thread("<m@x>", include_body=True)

    assert result["body"] == "hello"
    assert run_mock.call_args.args[1:] == ("<m@x>", "1", "177", "iCloud", "INBOX")


def test_mail_get_thread_degrades_to_store_metadata_on_body_timeout(monkeypatch):
    scoped = {
        "id": "<m@x>",
        "internal_id": "77",
        "mail_object_id": "177",
        "subject": "s",
        "sender": "a@b",
        "date": "2026-04-01T00:00:00",
        "mailbox_id": "imap://icloud/INBOX",
        "mailbox_path": "INBOX",
        "account_name": "iCloud",
        "attachments": [],
        "provider": "mail_store",
    }
    monkeypatch.setattr(mail, "_thread_scope_from_store", Mock(return_value=scoped))
    monkeypatch.setattr(mail, "run_applescript", Mock(side_effect=RuntimeError("AppleScript timed out")))

    result = mail.mail_get_thread("<m@x>", include_body=True)

    assert result["id"] == "<m@x>"
    assert result["body"] == ""
    assert result["body_available"] is False
    assert result["body_unavailable"] == "AppleScript timed out"
    assert result["attachments"] == []


def test_mail_get_thread_uses_store_body_fallback_on_applescript_failure(monkeypatch):
    scoped = {
        "id": "<m@x>",
        "internal_id": "77",
        "mail_object_id": "177",
        "subject": "s",
        "sender": "a@b",
        "date": "2026-04-01T00:00:00",
        "mailbox_id": "imap://icloud/INBOX",
        "mailbox_path": "INBOX",
        "account_name": "iCloud",
        "attachments": [],
        "provider": "mail_store",
    }
    monkeypatch.setattr(mail, "_thread_scope_from_store", Mock(return_value=scoped))
    monkeypatch.setattr(mail, "run_applescript", Mock(side_effect=RuntimeError("AppleScript failed (exit 1)")))
    monkeypatch.setattr(
        mail,
        "read_mail_store_message_body",
        Mock(
            return_value={
                "body": "fallback body",
                "body_content_type": "text/plain",
                "body_source": "mail_store_emlx",
            }
        ),
    )

    result = mail.mail_get_thread("<m@x>", include_body=True)

    assert result["body"] == "fallback body"
    assert result["body_available"] is True
    assert result["body_source"] == "mail_store_emlx"
    assert result["body_content_type"] == "text/plain"
    assert result["body_fallback_reason"] == "AppleScript failed (exit 1)"
    assert "body_unavailable" not in result


def test_mail_get_thread_uses_message_id_body_fallback_without_store_scope(monkeypatch):
    monkeypatch.setattr(mail, "_thread_scope_from_store", Mock(return_value=None))
    monkeypatch.setattr(mail, "run_applescript", Mock(side_effect=RuntimeError("AppleScript failed (exit 1)")))
    monkeypatch.setattr(
        mail,
        "read_mail_store_message_body_by_message_id",
        Mock(
            return_value={
                "id": "<m@x>",
                "message_id": "<m@x>",
                "subject": "fallback subject",
                "sender": "Sender <s@x>",
                "date": "2026-06-22T10:00:00+00:00",
                "body": "fallback by id",
                "body_content_type": "text/plain",
                "body_source": "mail_store_emlx",
            }
        ),
    )

    result = mail.mail_get_thread("m@x", include_body=True)

    assert result["id"] == "m@x"
    assert result["message_id"] == "m@x"
    assert result["subject"] == "fallback subject"
    assert result["sender"] == "Sender <s@x>"
    assert result["body"] == "fallback by id"
    assert result["body_available"] is True
    assert result["body_source"] == "mail_store_emlx"
    assert result["body_fallback_reason"] == "AppleScript failed (exit 1)"
    assert "body_unavailable" not in result


def test_mail_get_thread_uses_store_body_fallback_when_applescript_body_empty(monkeypatch):
    scoped = {
        "id": "<m@x>",
        "internal_id": "77",
        "mail_object_id": "177",
        "subject": "s",
        "sender": "a@b",
        "date": "2026-04-01T00:00:00",
        "mailbox_id": "imap://icloud/INBOX",
        "mailbox_path": "INBOX",
        "account_name": "iCloud",
        "attachments": [],
        "provider": "mail_store",
    }
    payload = dict(scoped)
    payload["body"] = ""
    monkeypatch.setattr(mail, "_thread_scope_from_store", Mock(return_value=scoped))
    monkeypatch.setattr(mail, "run_applescript", Mock(return_value=json.dumps(payload)))
    monkeypatch.setattr(
        mail,
        "read_mail_store_message_body",
        Mock(return_value={"body": "<p>fallback html</p>", "body_content_type": "text/html"}),
    )

    result = mail.mail_get_thread("<m@x>", include_body=True)

    assert result["body"] == "fallback html"
    assert result["body_available"] is True
    assert result["body_source"] == "mail_store_emlx"
    assert result["body_content_type"] == "text/html"
    assert result["body_fallback_reason"] == "AppleScript returned an empty body"


def test_mail_get_thread_degrades_without_store_scope_on_applescript_failure(monkeypatch):
    monkeypatch.setattr(mail, "_thread_scope_from_store", Mock(return_value=None))
    monkeypatch.setattr(mail, "run_applescript", Mock(side_effect=RuntimeError("AppleScript failed (exit 1)")))
    monkeypatch.setattr(mail, "read_mail_store_message_body_by_message_id", Mock(return_value=None))

    result = mail.mail_get_thread("m@example.com", include_body=True)

    assert result["id"] == "m@example.com"
    assert result["message_id"] == "m@example.com"
    assert result["body"] == ""
    assert result["body_available"] is False
    assert result["body_unavailable"] == "AppleScript failed (exit 1)"
    assert result["attachments"] == []
    assert result["open_url"] == "message://%3Cm%40example.com%3E"
    assert result["next_action"]["type"] == "open_url"


def test_mail_get_thread_degrades_when_applescript_returns_wrong_account(monkeypatch):
    scoped = {
        "id": "<m@x>",
        "internal_id": "77",
        "mail_object_id": "177",
        "subject": "s",
        "sender": "a@b",
        "date": "2026-04-01T00:00:00",
        "mailbox_id": "imap://icloud/INBOX",
        "mailbox_path": "INBOX",
        "account_name": "iCloud",
        "attachments": [],
        "provider": "mail_store",
    }
    payload = dict(scoped)
    payload["account_name"] = "Abhinav Hotmail"
    payload["body"] = "wrong account body"
    monkeypatch.setattr(mail, "_thread_scope_from_store", Mock(return_value=scoped))
    monkeypatch.setattr(mail, "run_applescript", Mock(return_value=json.dumps(payload)))

    result = mail.mail_get_thread("<m@x>", include_body=True)

    assert result["account_name"] == "iCloud"
    assert result["body"] == ""
    assert result["body_available"] is False
    assert "different account" in result["body_unavailable"]


def test_mail_get_thread_script_matches_internal_id_as_text():
    assert 'set msgList to messages of mb' in mail._GET_THREAD_SCRIPT
    assert 'set msgInternalId to (id of msg) as string' in mail._GET_THREAD_SCRIPT
    assert 'if msgInternalId is internalId then' in mail._GET_THREAD_SCRIPT
    assert 'tell application "Mail" to set msgMessageId to (message id of msg) as string' in mail._GET_THREAD_SCRIPT
    assert 'if my normalizeMessageId(msgMessageId) is mid then' in mail._GET_THREAD_SCRIPT
    assert 'set internalId to item 3 of argv' in mail._GET_THREAD_SCRIPT
    assert 'on normalizeMessageId(valueText)' in mail._GET_THREAD_SCRIPT
    assert 'set candidates to (messages of mb whose id is (internalId as integer))' not in mail._GET_THREAD_SCRIPT


# ---------------------------------------------------------------------------
# mail_send
# ---------------------------------------------------------------------------


def test_mail_send_dry_run_returns_preview(monkeypatch):
    run_mock = Mock()
    monkeypatch.setattr(mail, "run_applescript", run_mock)

    result = mail.mail_send(
        to=["a@b.com", "c@d.com"],
        subject="hi",
        body="body",
        cc=["e@f.com"],
        from_account="iCloud",
    )
    assert result["sent"] is False
    assert result["preview"]["to"] == ["a@b.com", "c@d.com"]
    assert result["preview"]["cc"] == ["e@f.com"]
    assert result["preview"]["subject"] == "hi"
    assert result["preview"]["from_account"] == "iCloud"
    assert result["next_action"]["tool"] == "mail_send"
    assert result["next_action"]["arguments"]["dry_run"] is False
    run_mock.assert_not_called()


def test_mail_send_actual_send_invokes_applescript(monkeypatch):
    run_mock = Mock(return_value=json.dumps({"success": True, "message_id": "<m@x>"}))
    monkeypatch.setattr(mail, "run_applescript", run_mock)
    monkeypatch.setattr(mail, "_known_account_names", lambda: ["iCloud"])

    result = mail.mail_send(
        to=["a@b.com"],
        subject="s",
        body="b",
        from_account="iCloud",
        dry_run=False,
    )
    assert result["sent"] is True
    assert result["message_id"] == "<m@x>"
    assert result["next_action"]["type"] == "open_app"
    run_mock.assert_called_once()

    args = run_mock.call_args.args
    assert args[1:] == ("s", "b", "iCloud", "1", "1", "0", "a@b.com")


def test_mail_send_rejects_unknown_from_account(monkeypatch):
    run_mock = Mock()
    monkeypatch.setattr(mail, "run_applescript", run_mock)
    monkeypatch.setattr(mail, "_known_account_names", lambda: ["iCloud", "Work"])

    with pytest.raises(RuntimeError, match="Unknown from_account"):
        mail.mail_send(
            to=["a@b.com"],
            subject="s",
            body="b",
            from_account="NotMine",
            dry_run=False,
        )
    run_mock.assert_not_called()


def test_mail_send_requires_recipient():
    with pytest.raises(RuntimeError, match="recipient"):
        mail.mail_send(to=[], subject="s", body="b")


def test_mail_send_without_account_skips_validation(monkeypatch):
    run_mock = Mock(return_value=json.dumps({"success": True, "message_id": ""}))
    monkeypatch.setattr(mail, "run_applescript", run_mock)
    called = {"n": 0}

    def boom():
        called["n"] += 1
        return []

    monkeypatch.setattr(mail, "_known_account_names", boom)
    mail.mail_send(to=["a@b.com"], subject="s", body="b", dry_run=False)
    assert called["n"] == 0


# ---------------------------------------------------------------------------
# mail_create_draft
# ---------------------------------------------------------------------------


def test_mail_create_draft_invokes_applescript(monkeypatch):
    run_mock = Mock(return_value=json.dumps({"success": True, "draft_created": True}))
    monkeypatch.setattr(mail, "run_applescript", run_mock)
    monkeypatch.setattr(mail, "_known_account_names", lambda: [])

    result = mail.mail_create_draft(
        to=["a@b.com", "c@d.com"],
        subject="s",
        body="b",
    )
    assert result["draft_created"] is True
    assert result["draft_visible"] is True
    assert result["open_mail"]["app"] == "Mail"
    assert result["next_step"] == "Review and send the visible draft in Mail."
    args = run_mock.call_args.args
    assert args[1:] == ("s", "b", "", "0", "2", "0", "a@b.com", "c@d.com")


def test_mail_create_draft_script_makes_drafts_visible():
    assert "visible:(not sendFlag)" in mail._SEND_SCRIPT
    assert "activate" in mail._SEND_SCRIPT
    assert '\\"draft_visible\\":true' in mail._SEND_SCRIPT
    assert '\\"open_mail\\"' in mail._SEND_SCRIPT


def test_mail_create_draft_requires_recipient():
    with pytest.raises(RuntimeError, match="recipient"):
        mail.mail_create_draft(to=[], subject="s", body="b")


# ---------------------------------------------------------------------------
# mail_open_message
# ---------------------------------------------------------------------------


def test_mail_open_message_dry_run_resolves_store_message(monkeypatch):
    row = {
        "id": "<m@x>",
        "subject": "Hello",
        "sender": "a@b",
        "date": "2026-04-01T00:00:00",
        "mailbox_id": "imap://icloud/INBOX",
        "mailbox_path": "INBOX",
        "account_name": "iCloud",
    }
    monkeypatch.setattr(mail, "get_mail_store_message", Mock(return_value=row))
    run_mock = Mock()
    monkeypatch.setattr(mail.subprocess, "run", run_mock)

    result = mail.mail_open_message("177", dry_run=True)

    assert result["opened"] is False
    assert result["dry_run"] is True
    assert result["message_id"] == "<m@x>"
    assert result["url"] == "message://%3Cm%40x%3E"
    assert result["open_url"] == "message://%3Cm%40x%3E"
    assert result["next_action"]["type"] == "open_url"
    assert result["account_name"] == "iCloud"
    run_mock.assert_not_called()


def test_mail_open_message_opens_message_url(monkeypatch):
    monkeypatch.setattr(mail, "get_mail_store_message", Mock(return_value=None))
    run_mock = Mock()
    monkeypatch.setattr(mail.subprocess, "run", run_mock)

    result = mail.mail_open_message("<m@x>")

    assert result["opened"] is True
    assert result["url"] == "message://%3Cm%40x%3E"
    assert result["open_url"] == "message://%3Cm%40x%3E"
    assert result["next_action"]["type"] == "open_app"
    run_mock.assert_called_once_with(["open", "message://%3Cm%40x%3E"], check=True, timeout=5)


def test_mail_open_message_wraps_bare_rfc_message_id_for_mail_url(monkeypatch):
    monkeypatch.setattr(mail, "get_mail_store_message", Mock(return_value=None))
    run_mock = Mock()
    monkeypatch.setattr(mail.subprocess, "run", run_mock)

    result = mail.mail_open_message("m@x")

    assert result["opened"] is True
    assert result["message_id"] == "m@x"
    assert result["url"] == "message://%3Cm%40x%3E"
    run_mock.assert_called_once_with(["open", "message://%3Cm%40x%3E"], check=True, timeout=5)


def test_mail_open_message_returns_unresolved_for_non_rfc_id(monkeypatch):
    monkeypatch.setattr(mail, "get_mail_store_message", Mock(return_value=None))

    result = mail.mail_open_message("177", dry_run=True)

    assert result["error"] == "message_id_unresolved"
    assert result["recoverable"] is True
    assert result["next_action"]["tool"] == "mail_search"


def test_mail_open_message_returns_structured_open_failure(monkeypatch):
    monkeypatch.setattr(mail, "get_mail_store_message", Mock(return_value=None))
    monkeypatch.setattr(mail.subprocess, "run", Mock(side_effect=OSError("no opener")))

    result = mail.mail_open_message("<m@x>")

    assert result["error"] == "mail_open_failed"
    assert result["opened"] is False
    assert result["recoverable"] is True


# ---------------------------------------------------------------------------
# mail_move_message
# ---------------------------------------------------------------------------


def test_mail_move_message_targets_by_id(monkeypatch):
    run_mock = Mock(
        side_effect=[
            json.dumps(
                [
                    {
                        "name": "Archive",
                        "id": "mb-archive",
                        "account_name": "iCloud",
                        "path": "Archive",
                        "writable": True,
                    }
                ]
            ),
            json.dumps({"success": True}),
        ]
    )
    monkeypatch.setattr(mail, "run_applescript", run_mock)

    result = mail.mail_move_message("<m@x>", "mb-archive")
    assert result["success"] is True
    assert result["message_id"] == "<m@x>"
    assert result["mailbox_id"] == "mb-archive"
    assert result["open_url"] == "message://%3Cm%40x%3E"
    assert result["next_action"]["tool"] == "mail_get_thread"
    args = run_mock.call_args.args
    assert args[1:] == ("<m@x>", "mb-archive")


def test_mail_move_message_resolves_friendly_mailbox_name(monkeypatch):
    run_mock = Mock(
        side_effect=[
            json.dumps(
                [
                    {
                        "name": "Archive",
                        "id": "mb-archive",
                        "account_name": "iCloud",
                        "path": "Archive",
                        "writable": True,
                    }
                ]
            ),
            json.dumps({"success": True}),
        ]
    )
    monkeypatch.setattr(mail, "run_applescript", run_mock)
    result = mail.mail_move_message("<m@x>", "Archive")
    assert result["success"] is True
    assert result["mailbox_id"] == "mb-archive"
    assert run_mock.call_args.args[1:] == ("<m@x>", "mb-archive")


def test_mail_move_message_returns_structured_ambiguous_mailbox_error(monkeypatch):
    run_mock = Mock(
        return_value=json.dumps(
            [
                {
                    "name": "Archive",
                    "id": "mb-1",
                    "account_name": "iCloud",
                    "path": "Archive",
                    "writable": True,
                },
                {
                    "name": "Archive",
                    "id": "mb-2",
                    "account_name": "Work",
                    "path": "Archive",
                    "writable": True,
                },
            ]
        )
    )
    monkeypatch.setattr(mail, "run_applescript", run_mock)
    result = mail.mail_move_message("<m@x>", "Archive")
    assert result["error"] == "target_ambiguous"
    assert len(result["candidates"]) == 2
    assert run_mock.call_count == 1


def test_mail_move_message_returns_structured_read_only_mailbox_error(monkeypatch):
    run_mock = Mock(
        return_value=json.dumps(
            [
                {
                    "name": "Archive",
                    "id": "mb-archive",
                    "account_name": "iCloud",
                    "path": "Archive",
                    "writable": False,
                }
            ]
        )
    )
    monkeypatch.setattr(mail, "run_applescript", run_mock)
    result = mail.mail_move_message("<m@x>", "Archive")
    assert result["error"] == "target_read_only"
    assert result["target"]["id"] == "mb-archive"


def test_mail_move_script_name_fallback_defines_mailbox_name():
    assert "set mbIdStr to mbName" not in mail._MOVE_SCRIPT
    assert "set mbIdStr to name of mb as string" in mail._MOVE_SCRIPT


# ---------------------------------------------------------------------------
# mail_flag_message
# ---------------------------------------------------------------------------


def test_mail_flag_message_sets_flag(monkeypatch):
    run_mock = Mock(return_value=json.dumps({"success": True}))
    monkeypatch.setattr(mail, "run_applescript", run_mock)

    result = mail.mail_flag_message("<m@x>", True)
    assert result["flagged"] is True
    assert result["message_id"] == "<m@x>"
    assert result["open_action"]["type"] == "open_url"
    args = run_mock.call_args.args
    assert args[1:] == ("<m@x>", "1")


def test_mail_flag_message_unsets_flag(monkeypatch):
    run_mock = Mock(return_value=json.dumps({"success": True}))
    monkeypatch.setattr(mail, "run_applescript", run_mock)

    result = mail.mail_flag_message("<m@x>", False)
    assert result["flagged"] is False
    args = run_mock.call_args.args
    assert args[1:] == ("<m@x>", "0")


# ---------------------------------------------------------------------------
# mail_delete
# ---------------------------------------------------------------------------


def test_mail_delete_by_canonical_id(monkeypatch):
    run_mock = Mock(return_value=json.dumps({"success": True}))
    monkeypatch.setattr(mail, "run_applescript", run_mock)

    result = mail.mail_delete("<m@x>", confirm=True)
    assert result["success"] is True
    assert result["message_id"] == "<m@x>"
    assert result["next_action"]["type"] == "open_app"
    args = run_mock.call_args.args
    assert args[1:] == ("<m@x>",)


def test_mail_delete_requires_confirmation(monkeypatch):
    run_mock = Mock(return_value=json.dumps({"success": True}))
    monkeypatch.setattr(mail, "run_applescript", run_mock)

    result = mail.mail_delete("<m@x>")
    assert result["preview"] == "Would delete message: <m@x>"
    assert result["confirmed"] is False
    assert result["next_action"]["tool"] == "mail_delete"
    assert result["next_action"]["arguments"] == {"message_id": "<m@x>", "confirm": True}
    run_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Bridge failure propagation (permission denials, etc.)
# ---------------------------------------------------------------------------


def test_bridge_runtime_error_propagates(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("AppleScript failed (exit 1)")

    monkeypatch.setattr(mail, "store_list_mailboxes", Mock(side_effect=MailStoreUnavailable("x", "x")))
    monkeypatch.setattr(mail, "run_applescript", boom)
    with pytest.raises(RuntimeError, match="AppleScript failed"):
        mail.mail_list_mailboxes()


def test_bridge_error_does_not_leak_stderr(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("AppleScript failed (exit 1)")

    monkeypatch.setattr(mail, "store_list_mailboxes", Mock(side_effect=MailStoreUnavailable("x", "x")))
    monkeypatch.setattr(mail, "run_applescript", boom)
    try:
        mail.mail_list_mailboxes()
    except RuntimeError as e:
        assert "exit 1" in str(e)
        for leak in ["Subject:", "invoice"]:
            assert leak not in str(e)


# ---------------------------------------------------------------------------
# Localization: mailbox targeting uses id, never name
# ---------------------------------------------------------------------------


def test_no_hardcoded_mailbox_display_names_in_source():
    """Fail loud if someone hardcodes INBOX/Sent/Drafts as AppleScript string literals."""
    import pathlib

    src = pathlib.Path(mail.__file__).read_text(encoding="utf-8")
    for banned in ['"INBOX"', '"Inbox"', '"Sent"', '"Drafts"', '"Trash"']:
        assert banned not in src, f"Hardcoded localized mailbox name: {banned}"
