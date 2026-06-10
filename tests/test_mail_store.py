from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from apple_ecosystem_mcp.mail_store import (
    MailSearchQuery,
    MailStoreUnavailable,
    search_mail_store,
)


def _create_mail_store(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            create table subjects (
                ROWID integer primary key autoincrement,
                subject text not null
            );
            create table addresses (
                ROWID integer primary key autoincrement,
                address text not null,
                comment text not null
            );
            create table mailboxes (
                ROWID integer primary key autoincrement,
                url text not null
            );
            create table messages (
                ROWID integer primary key autoincrement,
                message_id integer not null,
                global_message_id integer not null,
                sender integer,
                subject integer not null,
                date_received integer,
                mailbox integer not null,
                flags integer not null default 0,
                read integer not null default 0,
                flagged integer not null default 0,
                deleted integer not null default 0
            );
            create table message_global_data (
                ROWID integer primary key autoincrement,
                message_id integer,
                message_id_header text
            );
            create table attachments (
                ROWID integer primary key autoincrement,
                message integer not null,
                attachment_id text,
                name text
            );
            create table recipients (
                ROWID integer primary key,
                message integer not null,
                address integer not null,
                type integer,
                position integer
            );
            """
        )
        conn.executemany(
            "insert into subjects(ROWID, subject) values (?, ?)",
            [
                (1, "Quarterly receipt"),
                (2, "Older note"),
                (3, "Urgent update"),
            ],
        )
        conn.executemany(
            "insert into addresses(ROWID, address, comment) values (?, ?, ?)",
            [
                (1, "billing@example.com", "Billing"),
                (2, "ops@example.com", "Ops"),
                (3, "to@example.com", "Recipient"),
                (4, "cc@example.com", "Copy"),
            ],
        )
        conn.executemany(
            "insert into mailboxes(ROWID, url) values (?, ?)",
            [
                (1, "imap://ACCOUNT/Inbox"),
                (2, "imap://ACCOUNT/Archive"),
            ],
        )
        conn.executemany(
            """
            insert into messages(
                ROWID, message_id, global_message_id, sender, subject,
                date_received, mailbox, read, flagged, deleted
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (1, 101, 1001, 1, 1, 1_780_000_100, 1, 0, 0, 0),
                (2, 102, 1002, 2, 2, 1_780_000_000, 1, 1, 0, 0),
                (3, 103, 1003, 2, 3, 1_780_000_200, 2, 0, 1, 0),
                (4, 104, 1004, 2, 1, 1_780_000_300, 1, 0, 0, 1),
            ],
        )
        conn.executemany(
            "insert into message_global_data(message_id, message_id_header) values (?, ?)",
            [
                (101, "<receipt@example.com>"),
                (102, "<old@example.com>"),
                (103, "<urgent@example.com>"),
            ],
        )
        conn.execute("insert into attachments(message, attachment_id, name) values (1, 'a1', 'receipt.pdf')")
        conn.executemany(
            "insert into recipients(ROWID, message, address, type, position) values (?, ?, ?, ?, ?)",
            [
                (1, 1, 3, 0, 0),
                (2, 1, 4, 1, 0),
            ],
        )
        conn.commit()
    finally:
        conn.close()


def test_search_mail_store_returns_chronological_window(tmp_path):
    db_path = tmp_path / "Envelope Index"
    _create_mail_store(db_path)

    results = search_mail_store(
        MailSearchQuery(
            query="",
            limit=10,
            since="2026-05-28T13:28:00",
            unread=True,
        ),
        db_path=db_path,
    )

    assert [item["id"] for item in results] == ["<urgent@example.com>", "<receipt@example.com>"]
    assert [item["provider"] for item in results] == ["mail_store", "mail_store"]
    assert results[0]["date"] > results[1]["date"]


def test_search_mail_store_filters_subject_sender_and_attachments(tmp_path):
    db_path = tmp_path / "Envelope Index"
    _create_mail_store(db_path)

    results = search_mail_store(
        MailSearchQuery(
            query="billing",
            limit=10,
            search_subject=True,
            search_sender=True,
            has_attachments=True,
            to_addr="to@example.com",
            cc_addr="cc@example.com",
        ),
        db_path=db_path,
    )

    assert len(results) == 1
    assert results[0]["id"] == "<receipt@example.com>"
    assert results[0]["has_attachments"] is True
    assert results[0]["mailbox_id"] == "imap://ACCOUNT/Inbox"
    assert results[0]["mailbox_path"] == "Inbox"


def test_search_mail_store_filters_mailbox(tmp_path):
    db_path = tmp_path / "Envelope Index"
    _create_mail_store(db_path)

    results = search_mail_store(
        MailSearchQuery(query="", limit=10, mailbox_ids=("imap://ACCOUNT/Archive",)),
        db_path=db_path,
    )

    assert [item["id"] for item in results] == ["<urgent@example.com>"]


def test_search_mail_store_missing_db_returns_degraded_error(tmp_path):
    with pytest.raises(MailStoreUnavailable) as exc:
        search_mail_store(MailSearchQuery(query="", limit=10), db_path=tmp_path / "missing")

    assert exc.value.to_dict()["error"] == "mail_store_unavailable"


def test_search_mail_store_unsupported_schema(tmp_path):
    db_path = tmp_path / "Envelope Index"
    sqlite3.connect(db_path).close()

    with pytest.raises(MailStoreUnavailable) as exc:
        search_mail_store(MailSearchQuery(query="", limit=10), db_path=db_path)

    assert exc.value.to_dict()["error"] == "mail_store_unsupported_schema"
