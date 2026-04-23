from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from apple_ecosystem_mcp.tools import mail


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
        "mail_get_thread",
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
    assert tools["mail_get_thread"].annotations.readOnlyHint is True
    assert tools["mail_list_mailboxes"].annotations.readOnlyHint is True


def test_mail_delete_destructive_annotation():
    from apple_ecosystem_mcp import server

    tools = _inspect_tools(server.mcp)
    assert tools["mail_delete"].annotations.destructiveHint is True


# ---------------------------------------------------------------------------
# mail_list_mailboxes
# ---------------------------------------------------------------------------


def test_mail_list_mailboxes_returns_shape(monkeypatch):
    payload = [
        {"name": "INBOX", "id": "1A", "account_name": "iCloud"},
        {"name": "Sent", "id": "2B", "account_name": "iCloud"},
    ]
    monkeypatch.setattr(mail, "run_applescript", Mock(return_value=json.dumps(payload)))
    result = mail.mail_list_mailboxes()
    assert result == payload
    for mb in result:
        assert set(mb.keys()) == {"name", "id", "account_name"}


def test_mail_list_mailboxes_handles_empty(monkeypatch):
    monkeypatch.setattr(mail, "run_applescript", Mock(return_value=""))
    assert mail.mail_list_mailboxes() == []


def test_mail_list_mailboxes_rejects_non_list(monkeypatch):
    monkeypatch.setattr(mail, "run_applescript", Mock(return_value='{"oops": true}'))
    with pytest.raises(RuntimeError, match="payload"):
        mail.mail_list_mailboxes()


# ---------------------------------------------------------------------------
# mail_search
# ---------------------------------------------------------------------------


def _search_payload(n: int) -> str:
    items = [
        {
            "id": f"<msg-{i}@test>",
            "subject": f"subject {i}",
            "sender": f"s{i}@example.com",
            "date": "2026-04-01T10:00:00",
            "preview": "x" * 250,  # > _MAIL_PREVIEW_CHARS
            "mailbox_id": "mb-1",
            "account_name": "iCloud",
        }
        for i in range(n)
    ]
    return json.dumps(items)


def test_mail_search_default_and_argv(monkeypatch):
    run_mock = Mock(return_value=_search_payload(3))
    monkeypatch.setattr(mail, "run_applescript", run_mock)

    result = mail.mail_search("invoice")
    assert len(result) == 3
    args = run_mock.call_args.args
    assert args[1:] == ("invoice", "", "", "20")


def test_mail_search_forwards_mailbox_id_and_since(monkeypatch):
    run_mock = Mock(return_value="[]")
    monkeypatch.setattr(mail, "run_applescript", run_mock)
    mail.mail_search("q", mailbox_id="mb-7", since="2026-04-01T00:00:00", limit=10)
    args = run_mock.call_args.args
    assert args[1:] == ("q", "mb-7", "2026-04-01T00:00:00", "10")


def test_mail_search_caps_at_100(monkeypatch):
    run_mock = Mock(return_value=_search_payload(150))
    monkeypatch.setattr(mail, "run_applescript", run_mock)

    result = mail.mail_search("q", limit=500)
    assert len(result) == 100
    assert run_mock.call_args.args[-1] == "100"


def test_mail_search_preview_truncated_to_200(monkeypatch):
    monkeypatch.setattr(mail, "run_applescript", Mock(return_value=_search_payload(2)))
    result = mail.mail_search("q")
    for item in result:
        assert len(item["preview"]) == 200


def test_mail_search_returns_all_required_fields(monkeypatch):
    monkeypatch.setattr(mail, "run_applescript", Mock(return_value=_search_payload(1)))
    [item] = mail.mail_search("q")
    required = {"id", "subject", "sender", "date", "preview", "mailbox_id", "account_name"}
    assert required.issubset(item.keys())


def test_mail_search_minimum_limit_is_one(monkeypatch):
    run_mock = Mock(return_value="[]")
    monkeypatch.setattr(mail, "run_applescript", run_mock)
    mail.mail_search("q", limit=0)
    assert run_mock.call_args.args[-1] == "1"


# ---------------------------------------------------------------------------
# mail_get_thread
# ---------------------------------------------------------------------------


def test_mail_get_thread_plain_text_body(monkeypatch):
    payload = {
        "id": "<msg-1@test>",
        "subject": "hi",
        "sender": "a@b.com",
        "date": "2026-04-01T10:00:00",
        "body": "hello world",
        "mailbox_id": "mb-1",
        "account_name": "iCloud",
        "attachments": [],
    }
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
    monkeypatch.setattr(mail, "run_applescript", Mock(return_value=json.dumps(payload)))
    result = mail.mail_get_thread("<m@x>")
    assert "truncated" in result["body"]
    assert "4000 chars omitted" in result["body"]
    assert result["body"].startswith("x" * 100)


def test_mail_get_thread_include_body_false_omits_body(monkeypatch):
    payload = {
        "id": "<m@x>",
        "subject": "s",
        "sender": "a@b",
        "date": "2026-04-01T00:00:00",
        "mailbox_id": "mb",
        "account_name": "acct",
        "attachments": [],
    }
    run_mock = Mock(return_value=json.dumps(payload))
    monkeypatch.setattr(mail, "run_applescript", run_mock)
    result = mail.mail_get_thread("<m@x>", include_body=False)
    assert "body" not in result
    assert run_mock.call_args.args[1:] == ("<m@x>", "0")


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
    monkeypatch.setattr(mail, "run_applescript", Mock(return_value=json.dumps(payload)))
    result = mail.mail_get_thread("<m@x>")
    assert result["attachments"][0]["name"] == "report.pdf"
    assert result["attachments"][0]["size_bytes"] == 1024
    assert result["attachments"][0]["mime_type"] == "application/pdf"


def test_mail_get_thread_rejects_non_dict(monkeypatch):
    monkeypatch.setattr(mail, "run_applescript", Mock(return_value="[1,2,3]"))
    with pytest.raises(RuntimeError, match="payload"):
        mail.mail_get_thread("<m@x>")


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
    args = run_mock.call_args.args
    assert args[1:] == ("s", "b", "", "0", "2", "0", "a@b.com", "c@d.com")


def test_mail_create_draft_requires_recipient():
    with pytest.raises(RuntimeError, match="recipient"):
        mail.mail_create_draft(to=[], subject="s", body="b")


# ---------------------------------------------------------------------------
# mail_move_message
# ---------------------------------------------------------------------------


def test_mail_move_message_targets_by_id(monkeypatch):
    run_mock = Mock(return_value=json.dumps({"success": True}))
    monkeypatch.setattr(mail, "run_applescript", run_mock)

    result = mail.mail_move_message("<m@x>", "mb-archive")
    assert result["success"] is True
    assert result["message_id"] == "<m@x>"
    assert result["mailbox_id"] == "mb-archive"
    args = run_mock.call_args.args
    assert args[1:] == ("<m@x>", "mb-archive")


# ---------------------------------------------------------------------------
# mail_flag_message
# ---------------------------------------------------------------------------


def test_mail_flag_message_sets_flag(monkeypatch):
    run_mock = Mock(return_value=json.dumps({"success": True}))
    monkeypatch.setattr(mail, "run_applescript", run_mock)

    result = mail.mail_flag_message("<m@x>", True)
    assert result["flagged"] is True
    assert result["message_id"] == "<m@x>"
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

    result = mail.mail_delete("<m@x>")
    assert result["success"] is True
    assert result["message_id"] == "<m@x>"
    args = run_mock.call_args.args
    assert args[1:] == ("<m@x>",)


# ---------------------------------------------------------------------------
# Bridge failure propagation (permission denials, etc.)
# ---------------------------------------------------------------------------


def test_bridge_runtime_error_propagates(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("AppleScript failed (exit 1)")

    monkeypatch.setattr(mail, "run_applescript", boom)
    with pytest.raises(RuntimeError, match="AppleScript failed"):
        mail.mail_list_mailboxes()


def test_bridge_error_does_not_leak_stderr(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("AppleScript failed (exit 1)")

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
