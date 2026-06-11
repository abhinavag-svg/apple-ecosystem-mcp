from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from apple_ecosystem_mcp import mail_service
from apple_ecosystem_mcp.mail_store import MailStoreUnavailable


@pytest.fixture(autouse=True)
def _force_applescript_mail_provider(monkeypatch):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER", "applescript")


def _search_payload(n: int) -> str:
    items = [
        {
            "id": f"<msg-{i}@test>",
            "subject": f"subject {i}",
            "sender": f"s{i}@example.com",
            "date": "2026-04-01T10:00:00",
            "preview": "x" * 250,
            "mailbox_id": "mb-1",
            "account_name": "iCloud",
            "has_attachments": False,
        }
        for i in range(n)
    ]
    return json.dumps(items)


def test_search_mail_applescript_argv_and_preview_truncation(monkeypatch):
    run_mock = Mock(return_value=_search_payload(2))
    monkeypatch.setattr(mail_service, "run_applescript", run_mock)

    result = mail_service.search_mail("invoice")

    assert len(result) == 2
    for item in result:
        assert len(item["preview"]) == mail_service.MAIL_PREVIEW_CHARS
    assert run_mock.call_args.args[1:] == (
        "invoice",
        "",
        "",
        "20",
        "",
        "",
        "",
        "",
        "",
        "0",
        "",
        "0",
        "1",
        "0",
        "",
        "",
        "800",
        "0",
    )
    assert run_mock.call_args.kwargs["timeout"] == 35


def test_search_mail_caps_limit_at_100(monkeypatch):
    run_mock = Mock(return_value=_search_payload(150))
    monkeypatch.setattr(mail_service, "run_applescript", run_mock)

    result = mail_service.search_mail("q", limit=500)

    assert len(result) == 100
    assert run_mock.call_args.args[4] == "100"


def test_search_mail_forwards_fielded_filters(monkeypatch):
    run_mock = Mock(return_value="[]")
    monkeypatch.setattr(mail_service, "run_applescript", run_mock)

    mail_service.search_mail(
        "q",
        mailbox_id="mb-7",
        since="2026-04-01T00:00:00",
        before="2026-05-01T00:00:00",
        search_fields=["sender", "body"],
        filters={
            "from_addr": "sender@example.com",
            "to_addr": "recipient@example.com",
            "cc_addr": "cc@example.com",
            "unread": True,
            "flagged": True,
            "has_attachments": True,
            "account_name": "Work",
            "mailbox_ids": ["mb-1", "mb-2"],
        },
    )

    args = run_mock.call_args.args
    assert args[1:] == (
        "q",
        "mb-7",
        "2026-04-01T00:00:00",
        "20",
        "sender@example.com",
        "1",
        "1",
        "1",
        "Work",
        "1",
        "2026-05-01T00:00:00",
        "2",
        "mb-1",
        "mb-2",
        "0",
        "1",
        "recipient@example.com",
        "cc@example.com",
        "600",
        "0",
    )


def test_search_mail_local_provider_uses_store_for_metadata_queries(monkeypatch):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER", "local")
    run_mock = Mock(return_value="[]")
    store_mock = Mock(
        return_value=[
            {
                "id": "<local@test>",
                "subject": "Local",
                "sender": "a@example.com",
                "date": "2026-05-28T13:30:00",
                "preview": "",
                "mailbox_id": "imap://ACCOUNT/Inbox",
                "account_name": None,
                "has_attachments": False,
            }
        ]
    )
    monkeypatch.setattr(mail_service, "run_applescript", run_mock)
    monkeypatch.setattr(mail_service, "search_mail_store", store_mock)

    result = mail_service.search_mail("", since="2026-05-28T13:00:00", filters={"unread": True})

    assert result[0]["id"] == "<local@test>"
    search = store_mock.call_args.args[0]
    assert search.query == ""
    assert search.since == "2026-05-28T13:00:00"
    assert search.unread is True
    run_mock.assert_not_called()


def test_search_mail_local_provider_returns_degraded_state(monkeypatch):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER", "local")
    monkeypatch.setattr(mail_service, "run_applescript", Mock(return_value="[]"))

    def unavailable(_search):
        raise MailStoreUnavailable("mail_store_unavailable", "No index")

    monkeypatch.setattr(mail_service, "search_mail_store", unavailable)

    result = mail_service.search_mail("", since="2026-05-28T13:00:00")

    assert result == [
        {
            "error": "mail_store_unavailable",
            "message": "No index",
            "recoverable": True,
            "provider": "mail_store",
        }
    ]


def test_search_mail_auto_falls_back_to_applescript_when_store_unavailable(monkeypatch):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER", "auto")
    run_mock = Mock(return_value="[]")
    monkeypatch.setattr(mail_service, "run_applescript", run_mock)

    def unavailable(_search):
        raise MailStoreUnavailable("mail_store_unavailable", "No index")

    monkeypatch.setattr(mail_service, "search_mail_store", unavailable)

    assert mail_service.search_mail("", since="2026-05-28T13:00:00") == []
    run_mock.assert_called_once()


def test_search_mail_body_search_stays_on_applescript(monkeypatch):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER", "local")
    run_mock = Mock(return_value="[]")
    store_mock = Mock(return_value=[])
    monkeypatch.setattr(mail_service, "run_applescript", run_mock)
    monkeypatch.setattr(mail_service, "search_mail_store", store_mock)

    assert mail_service.search_mail("receipt", search_fields=["body"]) == []

    store_mock.assert_not_called()
    run_mock.assert_called_once()


def test_search_mail_local_account_scoping_uses_inventory_callback(monkeypatch):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER", "local")
    monkeypatch.setattr(
        mail_service,
        "list_mail_store_mailboxes",
        lambda: [
            {
                "mailbox_id": "imap://icloud/INBOX",
                "mailbox_url": "imap://icloud/INBOX",
                "mailbox_path": "INBOX",
                "account_token": "imap://icloud",
            },
            {
                "mailbox_id": "imap://icloud/Archive",
                "mailbox_url": "imap://icloud/Archive",
                "mailbox_path": "Archive",
                "account_token": "imap://icloud",
            },
            {
                "mailbox_id": "imap://hotmail/Inbox",
                "mailbox_url": "imap://hotmail/Inbox",
                "mailbox_path": "Inbox",
                "account_token": "imap://hotmail",
            },
        ],
    )
    seen = []

    def store(search):
        seen.append(search)
        return [
            {
                "id": "<fairmont@test>",
                "subject": "Fairmont",
                "sender": "Fairmont <x@test>",
                "date": "2026-06-10T17:02:21",
                "preview": "",
                "mailbox_id": "imap://icloud/INBOX",
                "mailbox_path": "INBOX",
                "account_name": None,
                "has_attachments": False,
                "provider": "mail_store",
            }
        ]

    monkeypatch.setattr(mail_service, "search_mail_store", store)
    monkeypatch.setattr(mail_service, "run_applescript", Mock(return_value="[]"))

    result = mail_service.search_mail(
        "Fairmont",
        search_fields=["sender", "subject"],
        filters={"account_name": "iCloud"},
        mailbox_inventory_fn=lambda: [
            {"id": "script-1", "name": "INBOX", "account_name": "iCloud", "path": "INBOX", "default_candidate": True},
            {"id": "script-2", "name": "Archive", "account_name": "iCloud", "path": "Archive", "default_candidate": False},
            {"id": "script-3", "name": "Inbox", "account_name": "Hotmail", "path": "Inbox", "default_candidate": True},
        ],
    )

    assert result[0]["account_name"] == "iCloud"
    assert seen[0].mailbox_ids == ("imap://icloud/INBOX", "imap://icloud/Archive")


def test_recent_mail_uses_local_store_without_query(monkeypatch):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER", "local")
    run_mock = Mock(return_value="[]")
    store_mock = Mock(
        return_value=[
            {
                "id": "<recent@test>",
                "subject": "Latest",
                "sender": "a@example.com",
                "date": "2026-06-11T09:01:57",
                "preview": "",
                "mailbox_id": "imap://icloud/INBOX",
                "account_name": "iCloud",
                "has_attachments": False,
            }
        ]
    )
    monkeypatch.setattr(mail_service, "run_applescript", run_mock)
    monkeypatch.setattr(mail_service, "_search_mail_store_scoped", store_mock)

    result = mail_service.recent_mail(limit=3)

    assert result[0]["id"] == "<recent@test>"
    assert store_mock.call_args.kwargs["query"] == ""
    assert store_mock.call_args.kwargs["since"] is None
    assert store_mock.call_args.kwargs["before"] is None
    run_mock.assert_not_called()
