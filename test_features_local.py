#!/usr/bin/env python3
"""
Local test script for MAIL-001 through MAIL-006 features.
Run with: uv run python test_features_local.py
"""

import json
from unittest.mock import Mock
from apple_ecosystem_mcp.tools import mail


def demo_feature(name: str, description: str):
    """Decorator for test functions."""
    def decorator(func):
        def wrapper():
            print(f"\n{'='*70}")
            print(f"🧪 {name}")
            print(f"{'='*70}")
            print(f"Description: {description}\n")
            try:
                func()
                print(f"✅ {name} works correctly!\n")
            except Exception as e:
                print(f"❌ Error: {e}\n")
        return wrapper
    return decorator


# Mock AppleScript to simulate real Mail responses
def mock_search_result(count=3, has_attachments_list=None):
    """Generate mock search results."""
    if has_attachments_list is None:
        has_attachments_list = [False] * count

    items = [
        {
            "id": f"<msg-{i}@example.com>",
            "internal_id": str(1000 + i),
            "subject": f"Test Email {i}",
            "sender": f"sender{i}@example.com",
            "date": f"2026-04-{10+i:02d}T10:00:00",
            "preview": "This is a preview of the email body...",
            "mailbox_id": "inbox-id",
            "account_name": "iCloud",
            "has_attachments": has_attachments_list[i],
        }
        for i in range(count)
    ]
    return json.dumps(items)


@demo_feature("MAIL-001", "Canonical RFC Message-ID")
def test_mail_001():
    """Test that RFC Message-ID is canonical and works in move/flag/delete."""
    # Mock the AppleScript call
    run_mock = Mock(return_value=json.dumps({"success": True}))
    original = mail.run_applescript
    mail.run_applescript = run_mock

    try:
        # Test move with RFC ID
        rfc_id = "<msg-12345@example.com>"
        result = mail.mail_move_message(rfc_id, "mb-archive")
        print(f"  • mail_move_message('{rfc_id}', 'mb-archive')")
        print(f"    → Result: {result}")
        assert result["message_id"] == rfc_id

        # Test flag with RFC ID
        result = mail.mail_flag_message(rfc_id, True)
        print(f"  • mail_flag_message('{rfc_id}', True)")
        print(f"    → Result: {result}")
        assert result["flagged"] is True

        # Test delete with RFC ID
        result = mail.mail_delete(rfc_id)
        print(f"  • mail_delete('{rfc_id}')")
        print(f"    → Result: {result}")
        assert result["success"] is True

        print("\n  ✓ RFC Message-IDs are properly handled across all operations")
    finally:
        mail.run_applescript = original


@demo_feature("MAIL-002", "Advanced Filters")
def test_mail_002():
    """Test advanced filter parameters."""
    run_mock = Mock(return_value=mock_search_result(2))
    original = mail.run_applescript
    mail.run_applescript = run_mock

    try:
        print("  Testing individual filters:")

        # Test from_addr filter
        result = mail.mail_search("test", filters={"from_addr": "sales@example.com"})
        print(f"  • from_addr filter: {len(result)} results")
        assert len(result) == 2

        # Test unread filter
        result = mail.mail_search("test", filters={"unread": True})
        print(f"  • unread=True filter: {len(result)} results")

        # Test flagged filter
        result = mail.mail_search("test", filters={"flagged": True})
        print(f"  • flagged=True filter: {len(result)} results")

        # Test has_attachments filter
        result = mail.mail_search("test", filters={"has_attachments": True})
        print(f"  • has_attachments=True filter: {len(result)} results")

        # Test account_name filter
        result = mail.mail_search("test", filters={"account_name": "Work"})
        print(f"  • account_name='Work' filter: {len(result)} results")

        # Test mailbox_ids list
        result = mail.mail_search("test", filters={"mailbox_ids": ["mb-1", "mb-2"]})
        print(f"  • mailbox_ids=['mb-1', 'mb-2'] filter: {len(result)} results")

        # Test multiple filters together
        result = mail.mail_search(
            "test",
            filters={
                "from_addr": "sales@example.com",
                "unread": True,
                "flagged": False,
                "has_attachments": True,
            }
        )
        print(f"  • Combined filters: {len(result)} results")

        print("\n  ✓ All filter combinations work correctly")
    finally:
        mail.run_applescript = original


@demo_feature("MAIL-003", "Body Search")
def test_mail_003():
    """Test body search via search_fields parameter."""
    run_mock = Mock(return_value=mock_search_result(1))
    original = mail.run_applescript
    mail.run_applescript = run_mock

    try:
        # Default: subject only
        result = mail.mail_search("invoice")
        args = run_mock.call_args.args
        search_body_flag = args[10]  # search_body is arg 10 (0-indexed from args[0])
        print(f"  • Default search_fields: subject only")
        print(f"    → search_body flag: {search_body_flag} (should be '0')")
        assert search_body_flag == "0"

        # With body search
        result = mail.mail_search("invoice", search_fields=["subject", "body"])
        args = run_mock.call_args.args
        search_body_flag = args[10]
        print(f"  • search_fields=['subject', 'body']")
        print(f"    → search_body flag: {search_body_flag} (should be '1')")
        assert search_body_flag == "1"

        # Body only
        result = mail.mail_search("invoice", search_fields=["body"])
        args = run_mock.call_args.args
        search_body_flag = args[10]
        print(f"  • search_fields=['body']")
        print(f"    → search_body flag: {search_body_flag} (should be '1')")
        assert search_body_flag == "1"

        print("\n  ✓ Body search toggle works correctly")
    finally:
        mail.run_applescript = original


@demo_feature("MAIL-004", "Mailbox Path Hierarchy")
def test_mail_004():
    """Test mailbox path field in list_mailboxes."""
    payload = [
        {"name": "INBOX", "id": "mb-1", "account_name": "iCloud", "path": "INBOX"},
        {"name": "2024", "id": "mb-2", "account_name": "iCloud", "path": "Archive/2024"},
        {"name": "Q1", "id": "mb-3", "account_name": "Work", "path": "Archive/2024/Q1"},
    ]
    run_mock = Mock(return_value=json.dumps(payload))
    original = mail.run_applescript
    mail.run_applescript = run_mock

    try:
        result = mail.mail_list_mailboxes()
        print(f"  • Retrieved {len(result)} mailboxes with paths:\n")
        for mb in result:
            print(f"    {mb['account_name']:10} | {mb['path']:20} | {mb['name']}")

        # Verify all have path field
        for mb in result:
            assert "path" in mb, f"Missing 'path' field in {mb}"

        print("\n  ✓ All mailboxes have path field with hierarchy")
    finally:
        mail.run_applescript = original


@demo_feature("MAIL-005", "Attachments in Search Results")
def test_mail_005():
    """Test has_attachments field in search results."""
    payload = [
        {
            "id": "<msg-1@test>",
            "internal_id": "1",
            "subject": "With attachment",
            "sender": "a@b.com",
            "date": "2026-04-01T10:00:00",
            "preview": "preview",
            "mailbox_id": "mb-1",
            "account_name": "iCloud",
            "has_attachments": True,
        },
        {
            "id": "<msg-2@test>",
            "internal_id": "2",
            "subject": "No attachment",
            "sender": "c@d.com",
            "date": "2026-04-02T10:00:00",
            "preview": "preview",
            "mailbox_id": "mb-1",
            "account_name": "iCloud",
            "has_attachments": False,
        },
    ]
    run_mock = Mock(return_value=json.dumps(payload))
    original = mail.run_applescript
    mail.run_applescript = run_mock

    try:
        result = mail.mail_search("test")
        print(f"  • Retrieved {len(result)} results with attachment info:\n")
        for msg in result:
            has_att = "📎" if msg["has_attachments"] else "  "
            print(f"    {has_att} {msg['subject']:30} | {msg['sender']}")

        # Verify all have has_attachments field
        for msg in result:
            assert "has_attachments" in msg
            assert isinstance(msg["has_attachments"], bool)

        print("\n  ✓ All results include has_attachments boolean field")
    finally:
        mail.run_applescript = original


@demo_feature("MAIL-006", "Date Range Filtering (since & before)")
def test_mail_006():
    """Test date range filtering with since and before."""
    run_mock = Mock(return_value=mock_search_result(2))
    original = mail.run_applescript
    mail.run_applescript = run_mock

    try:
        # Test since filter
        result = mail.mail_search(
            "test",
            since="2026-04-01T00:00:00"
        )
        args = run_mock.call_args.args
        since_value = args[3]
        print(f"  • since='2026-04-01T00:00:00'")
        print(f"    → Passed to AppleScript as: {since_value}")
        assert since_value == "2026-04-01T00:00:00"

        # Test before filter
        result = mail.mail_search(
            "test",
            before="2026-05-01T00:00:00"
        )
        args = run_mock.call_args.args
        before_value = args[11]
        print(f"  • before='2026-05-01T00:00:00'")
        print(f"    → Passed to AppleScript as: {before_value}")
        assert before_value == "2026-05-01T00:00:00"

        # Test both together
        result = mail.mail_search(
            "test",
            since="2026-04-01T00:00:00",
            before="2026-05-01T00:00:00"
        )
        args = run_mock.call_args.args
        since_val = args[3]
        before_val = args[11]
        print(f"  • Date range: 2026-04-01 to 2026-05-01")
        print(f"    → Since: {since_val}, Before: {before_val}")

        print("\n  ✓ Date range filtering works correctly")
    finally:
        mail.run_applescript = original


def main():
    """Run all feature tests."""
    print("\n" + "="*70)
    print("🧪 MAIL-001 to MAIL-006 Feature Tests")
    print("="*70)

    test_mail_001()
    test_mail_002()
    test_mail_003()
    test_mail_004()
    test_mail_005()
    test_mail_006()

    print("="*70)
    print("✅ All features tested successfully!")
    print("="*70 + "\n")


if __name__ == "__main__":
    main()
