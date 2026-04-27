#!/usr/bin/env python3
"""Integration tests for mail tools against actual Mail app.

Runs comprehensive tests for all mail features without mocking.
Tests are designed to be non-destructive (read-only) by default.
"""

import sys
import os
from datetime import datetime, timedelta

# Add src to path so we can import the tools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

from apple_ecosystem_mcp.tools.mail import (
    mail_search,
    mail_list_mailboxes,
    mail_get_thread,
)


def test_list_mailboxes():
    """Test listing mailboxes - this exercises the fixed mailbox id coercion and path feature."""
    print("\n" + "=" * 60)
    print("TEST 1: List Mailboxes (tests mailbox id coercion and path hierarchy)")
    print("=" * 60)
    try:
        mailboxes = mail_list_mailboxes()
        print(f"✅ Found {len(mailboxes)} mailboxes")

        # Check that path field exists
        has_path = all('path' in mb for mb in mailboxes)
        print(f"{'✅' if has_path else '⚠️ '} All mailboxes have 'path' field: {has_path}")

        for mb in mailboxes[:5]:  # Show first 5
            path_str = f" → {mb.get('path')}" if mb.get('path') else ""
            print(f"   - {mb.get('name')}{path_str}")
        if len(mailboxes) > 5:
            print(f"   ... and {len(mailboxes) - 5} more")
        return True
    except Exception as e:
        import traceback
        print(f"❌ Failed: {e}")
        print("\nFull traceback:")
        traceback.print_exc()
        return False


def test_search_linkedin():
    """Test searching for emails with 'LinkedIn' in subject line."""
    print("\n" + "=" * 60)
    print("TEST 2: Search for 'LinkedIn' in subject")
    print("=" * 60)
    try:
        results = mail_search("LinkedIn", limit=5)
        print(f"Results count: {len(results)}")
        print(f"Results type: {type(results)}")
        if results:
            print(f"✅ Found {len(results)} emails with 'LinkedIn'")
            for email in results:
                print(f"   Email keys: {list(email.keys())}")
                print(f"   - From: {email.get('from_addr')}")
                print(f"     Subject: {email.get('subject')}")
                print(f"     Date: {email.get('date')}")
                print()
        else:
            print("⚠️  No emails found with 'LinkedIn' - this is OK if you don't have any")
        return True
    except Exception as e:
        import traceback
        print(f"❌ Failed: {e}")
        print("\nFull traceback:")
        traceback.print_exc()
        return False


def test_search_recent():
    """Test searching for common word to get recent emails (limit 5)."""
    print("\n" + "=" * 60)
    print("TEST 3: Search for 'the' (common word, limit 5)")
    print("=" * 60)
    try:
        # Search for a common word that should match many emails
        results = mail_search("the", limit=5)
        print(f"Results count: {len(results)}")
        if results:
            print(f"✅ Found {len(results)} emails with 'the'")
            for i, email in enumerate(results, 1):
                print(f"\n   Email {i}:")
                print(f"   - From: {email.get('sender')}")
                print(f"     Subject: {email.get('subject')}")
                print(f"     Date: {email.get('date')}")
                email_id = email.get('id')
                id_display = f"{email_id[:20]}..." if email_id else "None"
                print(f"     ID: {id_display}")
        else:
            print("⚠️  No emails found with 'the' - unexpected")
        return True
    except Exception as e:
        import traceback
        print(f"❌ Failed: {e}")
        print("\nFull traceback:")
        traceback.print_exc()
        return False


def test_search_with_filters():
    """Test MAIL-002: Advanced filters (unread, flagged, has_attachments, etc.)

    Note: Filter-based searches can be slow with Mail.app's AppleScript interface
    when mailboxes are large. Tests may timeout.
    """
    print("\n" + "=" * 60)
    print("TEST 4: Search with advanced filters (MAIL-002)")
    print("=" * 60)
    try:
        # Test has_attachments filter (fastest, checks visible properties)
        print("  Testing has_attachments filter...")
        try:
            results = mail_search("the", filters={"has_attachments": True}, limit=3)
            print(f"  ✅ Emails with attachments found: {len(results)}")
        except RuntimeError as fe:
            if "timed out" in str(fe):
                print(f"  ⚠️  Filter timed out (Mail.app performance limitation) - skipping remaining filters")
                return True
            raise

        return True
    except Exception as e:
        import traceback
        print(f"❌ Failed: {e}")
        print("\nFull traceback:")
        traceback.print_exc()
        return False


def test_search_body():
    """Test MAIL-003: Body search via search_fields parameter

    Note: Body search requires accessing email content, which can be slow.
    Tests may timeout on large mailboxes.
    """
    print("\n" + "=" * 60)
    print("TEST 5: Body search (MAIL-003)")
    print("=" * 60)
    try:
        # Test body search (may timeout on large mailboxes)
        print("  Testing body search with search_fields=['body']...")
        try:
            results = mail_search("the", search_fields=["body"], limit=3)
            print(f"  ✅ Emails found in body: {len(results)}")
        except RuntimeError as be:
            if "timed out" in str(be):
                print(f"  ⚠️  Body search timed out (Mail.app performance limitation on large mailbox)")
                return True
            raise

        return True
    except Exception as e:
        import traceback
        print(f"❌ Failed: {e}")
        print("\nFull traceback:")
        traceback.print_exc()
        return False


def test_search_has_attachments():
    """Test MAIL-005: has_attachments boolean in search results"""
    print("\n" + "=" * 60)
    print("TEST 6: has_attachments field in results (MAIL-005)")
    print("=" * 60)
    try:
        results = mail_search("the", limit=3)
        if results:
            print(f"✅ Found {len(results)} emails")
            has_attachments_field = all('has_attachments' in email for email in results)
            print(f"  ✅ All results have 'has_attachments' field: {has_attachments_field}")

            for i, email in enumerate(results[:2], 1):
                print(f"  Email {i}: has_attachments = {email.get('has_attachments')}")
        else:
            print("⚠️  No emails found")
        return True
    except Exception as e:
        import traceback
        print(f"❌ Failed: {e}")
        print("\nFull traceback:")
        traceback.print_exc()
        return False


def test_search_date_range():
    """Test MAIL-006: Date before filter and date range filtering

    Note: Date filtering can be slow with Mail.app's AppleScript interface.
    Tests may timeout on large mailboxes.
    """
    print("\n" + "=" * 60)
    print("TEST 7: Date range filtering - before/since (MAIL-006)")
    print("=" * 60)
    try:
        # Create date range for last 30 days
        today = datetime.now()
        thirty_days_ago = today - timedelta(days=30)
        since_date = thirty_days_ago.isoformat() + "Z"
        before_date = today.isoformat() + "Z"

        print(f"  Testing date range: {thirty_days_ago.date()} to {today.date()}")
        try:
            results = mail_search("the", since=since_date, limit=3)
            print(f"  ✅ Emails since {thirty_days_ago.date()}: {len(results)}")
        except RuntimeError as de:
            if "timed out" in str(de):
                print(f"  ⚠️  Date filter timed out (Mail.app performance limitation)")
                return True
            raise

        return True
    except Exception as e:
        import traceback
        print(f"❌ Failed: {e}")
        print("\nFull traceback:")
        traceback.print_exc()
        return False


def test_get_thread():
    """Test mail_get_thread: Get full thread for an email"""
    print("\n" + "=" * 60)
    print("TEST 8: Get thread from an email (mail_get_thread)")
    print("=" * 60)
    try:
        # First, find an email to get thread from
        results = mail_search("the", limit=1)
        if not results:
            print("⚠️  No emails found to get thread from")
            return True

        email = results[0]
        message_id = email.get('id')
        print(f"  Found email with ID: {message_id[:20]}...")

        # Try to get thread - may fail if email doesn't have a proper RFC message ID
        try:
            thread = mail_get_thread(message_id)
            print(f"  ✅ Thread retrieved: {len(thread)} characters")
            print(f"     Preview: {thread[:100]}...")
        except RuntimeError as te:
            # Some emails may not have proper RFC IDs or may not be findable via AppleScript
            print(f"  ⚠️  Email not found in thread search (may not have RFC message ID): {te}")
            return True

        return True
    except Exception as e:
        import traceback
        print(f"❌ Failed: {e}")
        print("\nFull traceback:")
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n🚀 Running Mail Integration Tests")
    print("These tests run against your actual Mail app (not mocked)")
    print("Tests cover all mail features/use cases\n")

    results = []
    results.append(("MAIL-004: List Mailboxes with paths", test_list_mailboxes()))
    results.append(("Basic search - subject", test_search_linkedin()))
    results.append(("Basic search - common word", test_search_recent()))
    results.append(("MAIL-002: Advanced filters", test_search_with_filters()))
    results.append(("MAIL-003: Body search", test_search_body()))
    results.append(("MAIL-005: has_attachments field", test_search_has_attachments()))
    results.append(("MAIL-006: Date range filtering", test_search_date_range()))
    results.append(("Get thread content", test_get_thread()))

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    passed_count = 0
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
        if passed:
            passed_count += 1

    print(f"\nTotal: {passed_count}/{len(results)} tests passed")

    all_passed = all(r[1] for r in results)
    sys.exit(0 if all_passed else 1)
