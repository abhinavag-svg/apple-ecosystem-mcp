from __future__ import annotations

import sqlite3
import plistlib
from pathlib import Path

from apple_ecosystem_mcp import mail_store


def _create_minimal_mail_store(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            create table messages (
                ROWID integer primary key,
                message_id integer not null,
                global_message_id integer not null,
                sender integer,
                subject integer not null,
                mailbox integer not null,
                read integer not null default 0,
                flagged integer not null default 0,
                deleted integer not null default 0,
                date_received integer
            );
            create table subjects (ROWID integer primary key, subject text);
            create table addresses (ROWID integer primary key, address text not null, comment text not null);
            create table senders (ROWID integer primary key, contact_identifier text, bucket integer default 0, user_initiated integer default 1);
            create table sender_addresses (address integer primary key, sender integer not null);
            create table mailboxes (ROWID integer primary key, url text not null);
            create table message_global_data (message_id integer, message_id_header text);
            create table attachments (message integer);
            create table recipients (message integer, address integer, type integer);
            insert into messages (ROWID, message_id, global_message_id, subject, mailbox, read, flagged, deleted, date_received)
            values (1, 11, 21, 31, 41, 0, 0, 0, 1781202653);
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_inspect_mail_store_reports_success(tmp_path):
    db_path = tmp_path / "Envelope Index"
    _create_minimal_mail_store(db_path)

    result = mail_store.inspect_mail_store(db_path=db_path)

    assert result["ok"] is True
    assert result["exists"] is True
    assert result["provider"] == "mail_store"
    assert result["message_count"] == 1
    assert result["latest_date_received"] == "2026-06-11T11:30:53"
    assert result["missing_required_tables"] == []


def test_inspect_mail_store_reports_missing_db(tmp_path):
    result = mail_store.inspect_mail_store(db_path=tmp_path / "missing.db")

    assert result["ok"] is False
    assert result["error"] == "mail_store_unavailable"


def test_inspect_mail_store_reports_schema_issue(tmp_path):
    db_path = tmp_path / "Envelope Index"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("create table messages (ROWID integer primary key)")
        conn.commit()
    finally:
        conn.close()

    result = mail_store.inspect_mail_store(db_path=db_path)

    assert result["ok"] is False
    assert result["error"] == "mail_store_unsupported_schema"
    assert "subjects" in result["missing_required_tables"]


def test_refresh_mail_snapshot_creates_ephemeral_copy(tmp_path, monkeypatch):
    db_path = tmp_path / "Envelope Index"
    _create_minimal_mail_store(db_path)
    snapshot_root = tmp_path / "snapshots"
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_MAIL_SNAPSHOT_ROOT", str(snapshot_root))

    state = mail_store.refresh_mail_snapshot(source_path=db_path, ttl_seconds=60)

    assert Path(state["snapshot_db_path"]).exists()
    assert state["source_path"] == str(db_path)
    assert state["ttl_seconds"] == 60
    assert "Envelope Index" in state["copied_files"]
    persisted = mail_store.get_mail_snapshot_state()
    assert persisted is not None
    assert persisted["snapshot_db_path"] == state["snapshot_db_path"]


def test_inspect_mail_store_reports_snapshot_status(tmp_path, monkeypatch):
    db_path = tmp_path / "Envelope Index"
    _create_minimal_mail_store(db_path)
    snapshot_root = tmp_path / "snapshots"
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_MAIL_SNAPSHOT_ROOT", str(snapshot_root))
    mail_store.refresh_mail_snapshot(source_path=db_path, ttl_seconds=60)

    result = mail_store.inspect_mail_store(db_path=tmp_path / "missing.db")

    assert result["snapshot"]["available"] is True
    assert result["error"] == "mail_store_unavailable"


def test_search_mail_store_prefers_direct_sender_address_row(tmp_path):
    db_path = tmp_path / "Envelope Index"
    _create_minimal_mail_store(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("insert into subjects (ROWID, subject) values (?, ?)", (31, "Correct Subject"))
        conn.execute(
            "insert into addresses (ROWID, address, comment) values (?, ?, ?)",
            (101, "alerts@experian.com", "Experian"),
        )
        conn.execute(
            "insert into addresses (ROWID, address, comment) values (?, ?, ?)",
            (102, "dmurphy6@lululemon.com", "Daniel Murphy"),
        )
        conn.execute("update messages set sender = ? where ROWID = 1", (101,))
        conn.execute("insert into senders (ROWID, contact_identifier) values (?, ?)", (101, "sender-101"))
        conn.execute("insert into senders (ROWID, contact_identifier) values (?, ?)", (102, "sender-102"))
        conn.execute("insert into sender_addresses (address, sender) values (?, ?)", (102, 101))
        conn.commit()
    finally:
        conn.close()

    rows = mail_store.search_mail_store(mail_store.MailSearchQuery(query="", limit=5), db_path=db_path)

    assert rows[0]["subject"] == "Correct Subject"
    assert rows[0]["sender"] == "Experian <alerts@experian.com>"


def test_get_mail_store_message_matches_rfc_message_id(tmp_path):
    db_path = tmp_path / "Envelope Index"
    _create_minimal_mail_store(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("insert into subjects (ROWID, subject) values (?, ?)", (31, "Exact Match"))
        conn.execute(
            "insert into addresses (ROWID, address, comment) values (?, ?, ?)",
            (101, "news@echelon.com", "Echelon"),
        )
        conn.execute("update messages set sender = ? where ROWID = 1", (101,))
        conn.execute(
            "insert into message_global_data (message_id, message_id_header) values (?, ?)",
            (11, "<echelon@test>"),
        )
        conn.execute("insert into mailboxes (ROWID, url) values (?, ?)", (41, "ews://hotmail/Inbox"))
        conn.commit()
    finally:
        conn.close()

    row = mail_store.get_mail_store_message("<echelon@test>", db_path=db_path)

    assert row is not None
    assert row["id"] == "<echelon@test>"
    assert row["internal_id"] == "11"
    assert row["mail_object_id"] == "1"
    assert row["subject"] == "Exact Match"
    assert row["sender"] == "Echelon <news@echelon.com>"


def test_mail_account_map_reads_mail_preferences(tmp_path):
    preferences = tmp_path / "com.apple.mail.plist"
    preferences.write_bytes(
        plistlib.dumps(
            {
                "Accounts": [
                    {
                        "MailboxUidAccountURLString": "imap://ICLOUD-UUID/",
                        "MailboxUidName": "iCloud",
                        "MailboxUidPersistentIdentifier": "imap://ICLOUD-UUID/INBOX",
                    },
                    {
                        "MailboxUidAccountURLString": "ews://HOTMAIL-UUID/",
                        "MailboxUidName": "Abhinav Hotmail",
                        "MailboxUidPersistentIdentifier": "ews://HOTMAIL-UUID/Inbox",
                    },
                ]
            }
        )
    )

    mapping = mail_store.load_mail_account_map(
        preferences_path=preferences,
        accounts_db_path=tmp_path / "missing.sqlite",
    )

    assert mapping["imap://ICLOUD-UUID"] == "iCloud"
    assert mapping["ICLOUD-UUID"] == "iCloud"
    assert mapping["ews://HOTMAIL-UUID"] == "Abhinav Hotmail"


def test_mail_store_rows_include_account_name_from_preferences(tmp_path, monkeypatch):
    db_path = tmp_path / "Envelope Index"
    _create_minimal_mail_store(db_path)
    preferences = tmp_path / "com.apple.mail.plist"
    preferences.write_bytes(
        plistlib.dumps(
            {
                "Account": {
                    "MailboxUidAccountURLString": "imap://ICLOUD-UUID/",
                    "MailboxUidName": "iCloud",
                    "MailboxUidPersistentIdentifier": "imap://ICLOUD-UUID/INBOX",
                }
            }
        )
    )
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_MAIL_PREFERENCES", str(preferences))
    monkeypatch.setenv("APPLE_ECOSYSTEM_MCP_ACCOUNTS_DB", str(tmp_path / "missing.sqlite"))
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("insert into subjects (ROWID, subject) values (?, ?)", (31, "Mapped"))
        conn.execute("insert into mailboxes (ROWID, url) values (?, ?)", (41, "imap://ICLOUD-UUID/INBOX"))
        conn.commit()
    finally:
        conn.close()

    rows = mail_store.search_mail_store(mail_store.MailSearchQuery(query="", limit=5), db_path=db_path)
    mailboxes = mail_store.list_mail_store_mailboxes(db_path=db_path)

    assert rows[0]["account_name"] == "iCloud"
    assert rows[0]["account_token"] == "imap://ICLOUD-UUID"
    assert mailboxes[0]["account_name"] == "iCloud"


def test_inspect_mail_store_reports_permission_guidance(tmp_path, monkeypatch):
    db_path = tmp_path / "Envelope Index"
    _create_minimal_mail_store(db_path)

    def deny_open(self, *args, **kwargs):
        raise PermissionError()

    monkeypatch.setattr(Path, "open", deny_open)

    result = mail_store.inspect_mail_store(db_path=db_path)

    assert result["ok"] is False
    assert result["error"] == "mail_store_permission_denied"
    assert "Full Disk Access" in result["settings_path"]
    assert "refresh-snapshot" in result["next_step"]
