#!/usr/bin/env python3
"""Integration test for mail search against actual Mail app."""

import sys
import os

# Add src to path so we can import the tools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from apple_ecosystem_mcp.tools.mail import mail_search, mail_list_mailboxes


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


if __name__ == "__main__":
    print("\n🚀 Running Mail Integration Tests")
    print("These tests run against your actual Mail app (not mocked)")

    results = []
    results.append(("List Mailboxes", test_list_mailboxes()))
    results.append(("Search LinkedIn", test_search_linkedin()))
    results.append(("Search Recent", test_search_recent()))

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")

    all_passed = all(r[1] for r in results)
    sys.exit(0 if all_passed else 1)
