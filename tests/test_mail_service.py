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
        "1",
        "",
        "",
        "1600",
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

    args = run_mock.call_args.args[1:]
    assert args == (
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


def test_search_mail_normalizes_from_search_field_alias(monkeypatch):
    run_mock = Mock(return_value="[]")
    monkeypatch.setattr(mail_service, "run_applescript", run_mock)

    mail_service.search_mail("jobs-noreply@linkedin.com", search_fields=["from"])

    args = run_mock.call_args.args[1:]
    assert args[12] == "0"  # search_subject
    assert args[13] == "1"  # search_sender


def test_recent_mail_auto_normalizes_sender_filter_alias_for_applescript_and_store_fallback(monkeypatch):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER", "auto")
    run_mock = Mock(return_value="[]")
    store_mock = Mock(return_value=[])
    monkeypatch.setattr(mail_service, "run_applescript", run_mock)
    monkeypatch.setattr(mail_service, "search_mail_store", store_mock)

    result = mail_service.recent_mail(
        since="2026-06-19T00:00:00",
        before="2026-06-19T23:59:59",
        filters={"sender": "jobs-noreply@linkedin.com"},
        limit=20,
    )

    assert result == []
    args = run_mock.call_args.args[1:]
    assert args[4] == "jobs-noreply@linkedin.com"  # from_addr
    assert store_mock.call_args.args[0].from_addr == "jobs-noreply@linkedin.com"


def test_search_mail_normalizes_sender_filter_alias(monkeypatch):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER", "local")
    run_mock = Mock(return_value="[]")
    seen = []

    def store(search):
        seen.append(search)
        return []

    monkeypatch.setattr(mail_service, "run_applescript", run_mock)
    monkeypatch.setattr(mail_service, "search_mail_store", store)

    mail_service.recent_mail(
        since="2026-06-19T00:00:00",
        before="2026-06-19T23:59:59",
        filters={"sender": "jobs-noreply@linkedin.com"},
    )

    assert seen[0].from_addr == "jobs-noreply@linkedin.com"
    run_mock.assert_not_called()


def test_search_mail_default_fields_include_sender_for_local_store(monkeypatch):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER", "local")
    run_mock = Mock(return_value="[]")
    seen = []

    def store(search):
        seen.append(search)
        return [
            {
                "id": "<linkedin@test>",
                "subject": "Senior Director, Technology Transformation Lead at Marriott International",
                "sender": "LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>",
                "date": "2026-06-20T10:27:47",
                "preview": "",
                "mailbox_id": "imap://icloud/INBOX",
                "account_name": "iCloud",
                "has_attachments": False,
            }
        ]

    monkeypatch.setattr(mail_service, "run_applescript", run_mock)
    monkeypatch.setattr(mail_service, "search_mail_store", store)

    result = mail_service.search_mail("linkedin", since="2026-06-20T00:00:00")

    assert result[0]["id"] == "<linkedin@test>"
    assert seen[0].search_subject is True
    assert seen[0].search_sender is True
    run_mock.assert_not_called()


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
    monkeypatch.setattr(mail_service, "get_mail_snapshot_state", Mock(return_value=None))

    def unavailable(_search):
        raise MailStoreUnavailable("mail_store_unavailable", "No index")

    monkeypatch.setattr(mail_service, "search_mail_store", unavailable)

    result = mail_service.search_mail("", since="2026-05-28T13:00:00")

    assert result == [
        {
            "error": "mail_snapshot_required",
            "message": "Live Mail metadata is unavailable. Run refresh_mail_snapshot to create a temporary Mail snapshot for reads.",
            "recoverable": True,
            "provider": "mail_store",
            "live_error": "mail_store_unavailable",
            "snapshot_available": False,
        }
    ]


def test_search_mail_auto_uses_applescript_first(monkeypatch):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER", "auto")
    run_mock = Mock(
        return_value=json.dumps(
            [
                {
                    "id": "<script-linkedin@test>",
                    "subject": "Senior Director, Technology Transformation Lead at Marriott International",
                    "sender": "LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>",
                    "date": "2026-06-20T10:27:47",
                    "preview": "",
                    "mailbox_id": "icloud-inbox",
                    "account_name": "iCloud",
                    "has_attachments": False,
                }
            ]
        )
    )
    monkeypatch.setattr(mail_service, "run_applescript", run_mock)
    store_mock = Mock(return_value=[])
    monkeypatch.setattr(mail_service, "_search_mail_store_scoped", store_mock)

    result = mail_service.search_mail(
        "linkedin",
        since="2026-06-19T08:00:00",
        mailbox_inventory_fn=lambda: [
            {"id": "icloud-inbox", "name": "INBOX", "account_name": "iCloud", "path": "INBOX", "default_candidate": True},
            {"id": "icloud-archive", "name": "Archive", "account_name": "iCloud", "path": "Archive", "default_candidate": False},
        ],
    )

    assert result[0]["id"] == "<script-linkedin@test>"
    args = run_mock.call_args.args[1:]
    assert args[8] == "iCloud"
    assert args[11] == "1"
    assert args[12] == "icloud-inbox"
    assert store_mock.call_args.kwargs["query"] == "linkedin"
    assert store_mock.call_args.kwargs["since"] == "2026-06-19T08:00:00"


def test_search_mail_auto_falls_back_to_store_when_applescript_empty(monkeypatch):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER", "auto")
    run_mock = Mock(return_value="[]")
    monkeypatch.setattr(mail_service, "run_applescript", run_mock)
    store_mock = Mock(
        return_value=[
            {
                "id": "<store-linkedin@test>",
                "subject": "Senior Director, Technology Transformation Lead at Marriott International",
                "sender": "LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>",
                "date": "2026-06-20T10:27:47",
                "preview": "",
                "mailbox_id": "imap://icloud/INBOX",
                "account_name": "iCloud",
                "has_attachments": False,
            }
        ]
    )
    monkeypatch.setattr(mail_service, "_search_mail_store_scoped", store_mock)

    result = mail_service.search_mail("linkedin", since="2026-06-19T08:00:00")

    assert result[0]["id"] == "<store-linkedin@test>"
    assert result[0]["fallback_provider"] == "mail_store"
    assert result[0]["primary_provider_result"] == "applescript_empty"
    assert store_mock.call_args.kwargs["query"] == "linkedin"
    run_mock.assert_called()


def test_search_mail_auto_returns_degraded_when_trusted_metadata_unavailable(monkeypatch):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER", "auto")
    run_mock = Mock(return_value="[]")
    monkeypatch.setattr(mail_service, "run_applescript", run_mock)
    monkeypatch.setattr(mail_service, "get_mail_snapshot_state", Mock(return_value=None))

    def unavailable(_search):
        raise MailStoreUnavailable("mail_store_permission_denied", "Denied")

    monkeypatch.setattr(mail_service, "search_mail_store", unavailable)

    result = mail_service.search_mail("linkedin", since="2026-06-19T08:00:00")

    assert result == [
        {
            "error": "mail_snapshot_required",
            "message": "Live Mail metadata is unavailable. Run refresh_mail_snapshot to create a temporary Mail snapshot for reads.",
            "recoverable": True,
            "provider": "mail_store",
            "live_error": "mail_store_permission_denied",
            "snapshot_available": False,
            "next_step": "Run apple-ecosystem-mcp mail refresh-snapshot from Terminal, or grant Full Disk Access to the installed runtime.",
            "settings_path": "System Settings > Privacy & Security > Full Disk Access",
            "applescript_result_count": 0,
            "reason": "mail_search_requires_trusted_fallback",
        }
    ]
    run_mock.assert_called()


def test_recent_mail_auto_uses_applescript_first(monkeypatch):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER", "auto")
    run_mock = Mock(return_value=_search_payload(10))
    store_mock = Mock(return_value=[])
    monkeypatch.setattr(mail_service, "run_applescript", run_mock)
    monkeypatch.setattr(mail_service, "_search_mail_store_scoped", store_mock)

    result = mail_service.recent_mail(limit=10)

    assert result[0]["id"] == "<msg-0@test>"
    store_mock.assert_not_called()
    run_mock.assert_called_once()


def test_recent_mail_auto_returns_degraded_when_trusted_metadata_unavailable(monkeypatch):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER", "auto")
    run_mock = Mock(return_value="[]")
    monkeypatch.setattr(mail_service, "run_applescript", run_mock)
    monkeypatch.setattr(mail_service, "get_mail_snapshot_state", Mock(return_value=None))

    def unavailable(_search):
        raise MailStoreUnavailable("mail_store_permission_denied", "Denied")

    monkeypatch.setattr(mail_service, "search_mail_store", unavailable)

    result = mail_service.recent_mail(limit=10)

    assert result == [
        {
            "error": "mail_snapshot_required",
            "message": "Live Mail metadata is unavailable. Run refresh_mail_snapshot to create a temporary Mail snapshot for reads.",
            "recoverable": True,
            "provider": "mail_store",
            "live_error": "mail_store_permission_denied",
            "snapshot_available": False,
            "next_step": "Run apple-ecosystem-mcp mail refresh-snapshot from Terminal, or grant Full Disk Access to the installed runtime.",
            "settings_path": "System Settings > Privacy & Security > Full Disk Access",
            "applescript_result_count": 0,
            "reason": "recent_mail_requires_trusted_fallback",
        }
    ]
    run_mock.assert_called_once()


def test_search_mail_auto_returns_degraded_state_when_trusted_metadata_unavailable(monkeypatch):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER", "auto")
    run_mock = Mock(side_effect=RuntimeError("AppleScript timed out"))
    monkeypatch.setattr(mail_service, "run_applescript", run_mock)

    def unavailable(_search):
        raise MailStoreUnavailable("mail_store_unavailable", "No index")

    monkeypatch.setattr(mail_service, "search_mail_store", unavailable)
    monkeypatch.setattr(mail_service, "get_mail_snapshot_state", Mock(return_value=None))

    assert mail_service.search_mail("", since="2026-05-28T13:00:00") == [
        {
            "error": "mail_snapshot_required",
            "message": "Live Mail metadata is unavailable. Run refresh_mail_snapshot to create a temporary Mail snapshot for reads.",
            "recoverable": True,
            "provider": "mail_store",
            "live_error": "mail_store_unavailable",
            "snapshot_available": False,
            "applescript_error": "AppleScript timed out",
        }
    ]
    run_mock.assert_called_once()


def test_search_mail_permission_denied_returns_guidance(monkeypatch):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER", "auto")
    monkeypatch.setattr(mail_service, "run_applescript", Mock(side_effect=RuntimeError("AppleScript timed out")))
    monkeypatch.setattr(mail_service, "get_mail_snapshot_state", Mock(return_value=None))

    def unavailable(_search):
        raise MailStoreUnavailable("mail_store_permission_denied", "Denied")

    monkeypatch.setattr(mail_service, "search_mail_store", unavailable)

    assert mail_service.search_mail("", since="2026-05-28T13:00:00") == [
        {
            "error": "mail_snapshot_required",
            "message": "Live Mail metadata is unavailable. Run refresh_mail_snapshot to create a temporary Mail snapshot for reads.",
            "recoverable": True,
            "provider": "mail_store",
            "live_error": "mail_store_permission_denied",
            "snapshot_available": False,
            "next_step": "Run apple-ecosystem-mcp mail refresh-snapshot from Terminal, or grant Full Disk Access to the installed runtime.",
            "settings_path": "System Settings > Privacy & Security > Full Disk Access",
            "applescript_error": "AppleScript timed out",
        }
    ]


def test_search_mail_uses_snapshot_when_live_store_unavailable(monkeypatch):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER", "auto")
    run_mock = Mock(side_effect=RuntimeError("AppleScript timed out"))
    monkeypatch.setattr(mail_service, "run_applescript", run_mock)
    monkeypatch.setattr(
        mail_service,
        "get_mail_snapshot_state",
        Mock(return_value={"snapshot_db_path": "/tmp/mail-snapshot/Envelope Index"}),
    )
    monkeypatch.setattr(
        mail_service,
        "list_mail_store_mailboxes",
        lambda db_path=None: [
            {
                "mailbox_id": "imap://ACCOUNT/Inbox",
                "mailbox_url": "imap://ACCOUNT/Inbox",
                "mailbox_path": "Inbox",
                "account_token": "imap://ACCOUNT",
            }
        ],
    )
    calls = []

    def store(search, db_path=None):
        calls.append(db_path)
        if db_path is None:
            raise MailStoreUnavailable("mail_store_unavailable", "No live index")
        return [
            {
                "id": "<snapshot@test>",
                "subject": "Snapshot",
                "sender": "a@example.com",
                "date": "2026-05-28T13:30:00",
                "preview": "",
                "mailbox_id": "imap://ACCOUNT/Inbox",
                "account_name": None,
                "has_attachments": False,
            }
        ]

    monkeypatch.setattr(mail_service, "search_mail_store", store)

    result = mail_service.search_mail("", since="2026-05-28T13:00:00")

    assert result[0]["id"] == "<snapshot@test>"
    assert result[0]["fallback_provider"] == "mail_store"
    assert result[0]["primary_provider_error"] == "AppleScript timed out"
    assert calls == [None, "/tmp/mail-snapshot/Envelope Index"]
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


def test_search_mail_explicit_applescript_provider_bypasses_store(monkeypatch):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER", "auto")
    run_mock = Mock(return_value="[]")
    store_mock = Mock(return_value=[])
    monkeypatch.setattr(mail_service, "run_applescript", run_mock)
    monkeypatch.setattr(mail_service, "search_mail_store", store_mock)

    assert mail_service.search_mail("invoice", filters={"provider": "applescript"}) == []

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
    assert seen[0].mailbox_ids == ("imap://icloud/INBOX",)


def test_search_mail_account_scope_requires_inventory(monkeypatch):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER", "local")
    monkeypatch.setattr(
        mail_service,
        "list_mail_store_mailboxes",
        lambda db_path=None: [
            {
                "mailbox_id": "imap://hotmail/Inbox",
                "mailbox_url": "imap://hotmail/Inbox",
                "mailbox_path": "Inbox",
                "account_token": "imap://hotmail",
                "account_name": "Abhinav Hotmail",
            },
        ],
    )
    monkeypatch.setattr(mail_service, "run_applescript", Mock(return_value="[]"))

    result = mail_service.recent_mail(
        since="2026-06-11T00:00:00",
        filters={"account_name": "iCloud"},
        mailbox_inventory_fn=lambda: [],
    )

    assert result[0]["error"] == "mail_snapshot_required"
    assert result[0]["live_error"] == "mail_account_scope_unavailable"


def test_search_mail_account_scope_uses_store_account_names_without_inventory(monkeypatch):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER", "local")
    monkeypatch.setattr(
        mail_service,
        "list_mail_store_mailboxes",
        lambda db_path=None: [
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
        ],
    )
    seen = []

    def store(search):
        seen.append(search)
        return [
            {
                "id": "<icloud@test>",
                "subject": "Scoped",
                "sender": "x@example.com",
                "date": "2026-06-11T15:00:25",
                "preview": "",
                "mailbox_id": "imap://icloud/INBOX",
                "mailbox_path": "INBOX",
                "account_name": "iCloud",
                "has_attachments": False,
                "provider": "mail_store",
            }
        ]

    monkeypatch.setattr(mail_service, "search_mail_store", store)
    monkeypatch.setattr(mail_service, "run_applescript", Mock(return_value="[]"))

    result = mail_service.recent_mail(
        since="2026-06-11T00:00:00",
        filters={"account_name": "iCloud"},
        mailbox_inventory_fn=lambda: [],
    )

    assert result[0]["id"] == "<icloud@test>"
    assert seen[0].mailbox_ids == ("imap://icloud/INBOX",)


def test_search_mail_resolves_friendly_mailbox_ids_within_scoped_account(monkeypatch):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER", "local")
    monkeypatch.setattr(
        mail_service,
        "list_mail_store_mailboxes",
        lambda db_path=None: [
            {
                "mailbox_id": "imap://icloud/INBOX",
                "mailbox_url": "imap://icloud/INBOX",
                "mailbox_path": "INBOX",
                "account_token": "imap://icloud",
            },
            {
                "mailbox_id": "ews://hotmail/Inbox",
                "mailbox_url": "ews://hotmail/Inbox",
                "mailbox_path": "Inbox",
                "account_token": "ews://hotmail",
            },
        ],
    )
    seen = []

    def store(search):
        seen.append(search)
        return [
            {
                "id": "<icloud@test>",
                "subject": "Scoped",
                "sender": "x@example.com",
                "date": "2026-06-11T15:00:25",
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
        "",
        since="2026-06-11T00:00:00",
        filters={"account_name": "iCloud", "mailbox_ids": ["INBOX"]},
        mailbox_inventory_fn=lambda: [
            {"id": "script-1", "name": "INBOX", "account_name": "iCloud", "path": "INBOX", "default_candidate": True},
            {"id": "script-2", "name": "Inbox", "account_name": "Hotmail", "path": "Inbox", "default_candidate": True},
        ],
    )

    assert seen[0].mailbox_ids == ("imap://icloud/INBOX",)
    assert result[0]["account_name"] == "iCloud"


def test_search_mail_preserves_canonical_store_mailbox_ids(monkeypatch):
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER", "local")
    seen = []

    def store(search):
        seen.append(search)
        return []

    monkeypatch.setattr(mail_service, "search_mail_store", store)
    monkeypatch.setattr(mail_service, "run_applescript", Mock(return_value="[]"))

    mail_service.search_mail(
        "",
        filters={"account_name": "iCloud", "mailbox_ids": ["imap://icloud/INBOX"]},
        mailbox_inventory_fn=lambda: [],
    )

    assert seen[0].mailbox_ids == ("imap://icloud/INBOX",)


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


def test_recent_mail_applescript_scopes_per_account_inboxes(monkeypatch):
    calls = []

    def run(script, *args, timeout):
        calls.append((args, timeout))
        account = args[8]
        payload = [
            {
                "id": f"<{account.lower()}@test>",
                "subject": account,
                "sender": f"{account.lower()}@example.com",
                "date": "2026-06-11T09:01:57",
                "preview": "",
                "mailbox_id": args[12],
                "account_name": account,
                "has_attachments": False,
            }
        ]
        return json.dumps(payload)

    monkeypatch.setattr(mail_service, "run_applescript", run)

    result = mail_service.recent_mail(
        limit=5,
        since="2026-06-11T00:00:00",
        mailbox_inventory_fn=lambda: [
            {"id": "icloud-inbox", "name": "INBOX", "account_name": "iCloud", "path": "INBOX", "default_candidate": True},
            {"id": "icloud-archive", "name": "Archive", "account_name": "iCloud", "path": "Archive", "default_candidate": False},
            {"id": "hotmail-inbox", "name": "Inbox", "account_name": "Hotmail", "path": "Inbox", "default_candidate": True},
        ],
    )

    assert [item["account_name"] for item in result] == ["iCloud", "Hotmail"]
    assert len(calls) == 2
    assert calls[0][0][8] == "iCloud"
    assert calls[0][0][11] == "1"
    assert calls[0][0][12] == "icloud-inbox"
    assert calls[0][0][5] == ""
    assert calls[0][1] == 18
    assert calls[1][0][8] == "Hotmail"
    assert calls[1][0][12] == "hotmail-inbox"
    assert calls[1][0][5] == ""


def test_recent_mail_applescript_returns_partial_results_after_one_timeout(monkeypatch):
    calls = []

    def run(script, *args, timeout):
        calls.append((args, timeout))
        account = args[8]
        if account == "Hotmail":
            raise RuntimeError("AppleScript timed out")
        return json.dumps(
            [
                {
                    "id": "<icloud@test>",
                    "subject": "iCloud",
                    "sender": "icloud@example.com",
                    "date": "2026-06-11T09:01:57",
                    "preview": "",
                    "mailbox_id": "icloud-inbox",
                    "account_name": "iCloud",
                    "has_attachments": False,
                }
            ]
        )

    monkeypatch.setattr(mail_service, "run_applescript", run)

    result = mail_service.recent_mail(
        limit=5,
        since="2026-06-11T00:00:00",
        mailbox_inventory_fn=lambda: [
            {"id": "icloud-inbox", "name": "INBOX", "account_name": "iCloud", "path": "INBOX", "default_candidate": True},
            {"id": "hotmail-inbox", "name": "Inbox", "account_name": "Hotmail", "path": "Inbox", "default_candidate": True},
        ],
    )

    assert result == [
        {
            "id": "<icloud@test>",
            "subject": "iCloud",
            "sender": "icloud@example.com",
            "date": "2026-06-11T09:01:57",
            "preview": "",
            "mailbox_id": "icloud-inbox",
            "account_name": "iCloud",
            "has_attachments": False,
        }
    ]
    assert len(calls) == 3
    assert calls[1][0][8] == "Hotmail"
    assert calls[1][0][11] == "1"
    assert calls[2][0][8] == "Hotmail"
    assert calls[2][0][11] == "0"


def test_recent_mail_applescript_retries_account_only_when_mailbox_scoped_empty(monkeypatch):
    calls = []

    def run(script, *args, timeout):
        calls.append((args, timeout))
        mailbox_count = args[11]
        if mailbox_count == "1":
            return "[]"
        return json.dumps(
            [
                {
                    "id": "<account-only@test>",
                    "subject": "account-only",
                    "sender": "icloud@example.com",
                    "date": "2026-06-11T09:01:57",
                    "preview": "",
                    "mailbox_id": "fallback",
                    "account_name": "iCloud",
                    "has_attachments": False,
                }
            ]
        )

    monkeypatch.setattr(mail_service, "run_applescript", run)

    result = mail_service.recent_mail(
        limit=5,
        since="2026-06-11T00:00:00",
        filters={"account_name": "iCloud"},
        mailbox_inventory_fn=lambda: [
            {"id": "icloud-inbox", "name": "INBOX", "account_name": "iCloud", "path": "INBOX", "default_candidate": True},
            {"id": "icloud-archive", "name": "Archive", "account_name": "iCloud", "path": "Archive", "default_candidate": False},
        ],
    )

    assert [item["id"] for item in result] == ["<account-only@test>"]
    assert len(calls) == 2
    assert calls[0][0][11] == "1"
    assert calls[1][0][11] == "0"


def test_search_mail_applescript_prefilters_sender_candidates(monkeypatch):
    run_mock = Mock(return_value="[]")
    monkeypatch.setattr(mail_service, "run_applescript", run_mock)

    mail_service.search_mail(
        "school pickup",
        filters={"from_addr": "Ankita"},
        since="2026-06-11T00:00:00",
    )

    args = run_mock.call_args.args
    assert args[5] == "Ankita"


def test_recent_mail_applescript_re_raises_timeout_when_every_account_fails(monkeypatch):
    monkeypatch.setattr(
        mail_service,
        "run_applescript",
        Mock(side_effect=RuntimeError("AppleScript timed out")),
    )

    with pytest.raises(RuntimeError, match="timed out"):
        mail_service.recent_mail(
            limit=5,
            since="2026-06-11T00:00:00",
            mailbox_inventory_fn=lambda: [
                {"id": "icloud-inbox", "name": "INBOX", "account_name": "iCloud", "path": "INBOX", "default_candidate": True},
            ],
        )
