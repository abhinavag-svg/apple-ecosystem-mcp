from __future__ import annotations

from pathlib import Path

from apple_ecosystem_mcp.prompt_contract import (
    MAIL_RECENT_CONTRACT,
    MAIL_SEARCH_CONTRACT,
    PROMPT_EXAMPLES,
    tool_contract,
)


def test_tool_contract_lookup_returns_mail_metadata():
    assert tool_contract("mail_search") == MAIL_SEARCH_CONTRACT
    assert tool_contract("mail_recent") == MAIL_RECENT_CONTRACT
    assert "literal query text" in MAIL_SEARCH_CONTRACT.description
    assert "ask a follow-up" in MAIL_SEARCH_CONTRACT.description
    assert "chronological order" in MAIL_RECENT_CONTRACT.description


def test_prompt_examples_cover_canonical_mail_routing():
    expected = {
        "What emails did I receive overnight in iCloud?": "mail_recent",
        "What unread emails came in since 10 PM last night?": "mail_recent",
        "Find emails from Ankita about school pickup.": "mail_search",
        "Search my mail for receipts from Apple with attachments.": "mail_search",
    }
    actual = {entry.prompt: entry.preferred_tool for entry in PROMPT_EXAMPLES}
    for prompt, tool in expected.items():
        assert actual[prompt] == tool


def test_prompt_dictionary_doc_stays_aligned_with_packaged_contract():
    doc = Path("docs/claude-prompt-dictionary.md").read_text(encoding="utf-8")
    for entry in PROMPT_EXAMPLES:
        assert entry.prompt in doc
    for fragment in ("guessed keyword bundles", "same-named targets"):
        assert fragment in doc
