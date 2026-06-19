"""Integration tests for mail tools against a real local Mail.app setup.

These tests are read-only and intentionally lightweight, but they still depend
on local mailbox contents and Mail.app responsiveness.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import pytest

from apple_ecosystem_mcp.tools.mail import (
    mail_get_thread,
    mail_list_mailboxes,
    mail_open_message,
    mail_recent,
    mail_search,
)


pytestmark = pytest.mark.skipif(
    os.environ.get("APPLE_MCP_LIVE_TESTS") != "1",
    reason="requires local Mail.app integration; set APPLE_MCP_LIVE_TESTS=1",
)


def test_list_mailboxes():
    """Exercise mailbox enumeration and hierarchy metadata."""
    mailboxes = mail_list_mailboxes()
    assert isinstance(mailboxes, list)
    if mailboxes:
        assert all("path" in mailbox for mailbox in mailboxes)


def test_search_linkedin():
    """Exercise a narrow subject search."""
    results = mail_search("LinkedIn", limit=5)
    assert isinstance(results, list)
    for email in results:
        assert "subject" in email
        assert "date" in email


def test_search_recent():
    """Exercise a broad subject search against real data."""
    results = mail_search("the", limit=5)
    assert isinstance(results, list)
    for email in results:
        assert "id" in email
        assert "sender" in email
        assert "subject" in email


def test_search_with_filters():
    """Exercise MAIL-002 filters against real data."""
    try:
        results = mail_search("the", filters={"has_attachments": True}, limit=3)
    except RuntimeError as exc:
        if "timed out" in str(exc):
            pytest.skip("Mail.app filter integration timed out on local mailbox data")
        raise
    assert isinstance(results, list)


def test_search_body():
    """Exercise MAIL-003 body search against real data."""
    try:
        results = mail_search("the", search_fields=["body"], limit=3)
    except RuntimeError as exc:
        if "timed out" in str(exc):
            pytest.skip("Mail.app body-search integration timed out on local mailbox data")
        raise
    assert isinstance(results, list)


def test_search_has_attachments():
    """Exercise MAIL-005 attachment metadata in result rows."""
    results = mail_search("the", limit=3)
    assert isinstance(results, list)
    for email in results:
        assert "has_attachments" in email


def test_search_date_range():
    """Exercise MAIL-006 date filtering against real data."""
    try:
        today = datetime.now()
        thirty_days_ago = today - timedelta(days=30)
        since_date = thirty_days_ago.isoformat() + "Z"
        results = mail_search("the", since=since_date, limit=3)
    except RuntimeError as exc:
        if "timed out" in str(exc):
            pytest.skip("Mail.app date-filter integration timed out on local mailbox data")
        raise
    assert isinstance(results, list)


def test_recent_icloud_inbox_last_10_hours(monkeypatch):
    """Exercise deterministic local-store account and inbox scoping."""
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER", "local")
    since = (datetime.now().astimezone() - timedelta(hours=10)).isoformat(timespec="seconds")
    results = mail_recent(limit=10, since=since, filters={"account_name": "iCloud"})
    if results and isinstance(results[0], dict) and results[0].get("error"):
        pytest.skip(f"Local Mail store unavailable: {results[0].get('live_error') or results[0].get('error')}")
    if not results:
        pytest.skip("No iCloud inbox messages in the last 10 hours")

    assert {email.get("account_name") for email in results} == {"iCloud"}
    assert {str(email.get("mailbox_path")).casefold() for email in results} == {"inbox"}

    thread = mail_get_thread(str(results[0]["id"]), include_body=False)
    assert isinstance(thread, dict)
    assert thread["id"] == results[0]["id"]
    assert thread["account_name"] == "iCloud"
    assert str(thread.get("mailbox_path")).casefold() == "inbox"
    assert "body" not in thread

    opener = mail_open_message(str(results[0]["id"]), dry_run=True)
    assert opener["message_id"] == results[0]["id"]
    assert opener["url"].startswith("message://")
    assert opener["opened"] is False


def test_get_thread():
    """Exercise thread fetching for a locally discoverable message."""
    results = mail_search("the", limit=1)
    if not results:
        pytest.skip("No local Mail messages available for thread integration test")

    message_id = results[0].get("id")
    assert message_id

    try:
        thread = mail_get_thread(message_id, include_body=False)
    except RuntimeError as exc:
        if "timed out" in str(exc):
            pytest.skip("Mail.app thread integration timed out on local mailbox data")
        if "not found" in str(exc).lower():
            pytest.skip("Selected Mail message could not be resolved back to a thread")
        raise

    assert isinstance(thread, dict)
    assert thread.get("id")
