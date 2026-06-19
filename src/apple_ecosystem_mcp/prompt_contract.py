from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolContract:
    tool_name: str
    title: str
    description: str


@dataclass(frozen=True)
class PromptExample:
    prompt: str
    intent_category: str
    preferred_tool: str
    guidance: str


MAIL_SEARCH_CONTRACT = ToolContract(
    tool_name="mail_search",
    title="Search Mail",
    description=(
        "Search Mail by literal query text or explicit fielded filters. "
        "Use this tool for keyword-style lookups such as sender, subject, or body search. "
        "For chronological retrieval, prefer mail_recent instead of inventing keywords. "
        "If the user asks for mail from a sender and does not give a time window, ask a follow-up "
        "for since and/or before rather than running an unbounded sender search. "
        "If you already have the window, pass the user's literal query string and constrain it "
        "with since and/or before."
    ),
)

MAIL_RECENT_CONTRACT = ToolContract(
    tool_name="mail_recent",
    title="Recent Mail",
    description=(
        "Return the most recent Mail messages in chronological order. "
        "Use this tool for recency-style requests such as latest, recent, overnight, or today. "
        "Do not synthesize topic keywords; instead pass explicit since/before bounds and optional "
        "structured filters such as account_name, mailbox_ids, or unread."
    ),
)

TOOL_CONTRACTS: dict[str, ToolContract] = {
    MAIL_SEARCH_CONTRACT.tool_name: MAIL_SEARCH_CONTRACT,
    MAIL_RECENT_CONTRACT.tool_name: MAIL_RECENT_CONTRACT,
}

PROMPT_EXAMPLES: tuple[PromptExample, ...] = (
    PromptExample(
        prompt="What emails did I receive overnight in iCloud?",
        intent_category="mail_recent",
        preferred_tool="mail_recent",
        guidance="Use explicit since/before bounds and account_name; do not invent keywords.",
    ),
    PromptExample(
        prompt="What unread emails came in since 10 PM last night?",
        intent_category="mail_recent",
        preferred_tool="mail_recent",
        guidance="Use explicit since and unread=true.",
    ),
    PromptExample(
        prompt="Find emails from Ankita about school pickup.",
        intent_category="mail_search",
        preferred_tool="mail_search",
        guidance="Ask for a time window first if none is provided; then use the literal topic query and fielded sender filter.",
    ),
    PromptExample(
        prompt="Search my mail for receipts from Apple with attachments.",
        intent_category="mail_search",
        preferred_tool="mail_search",
        guidance="Use literal receipt query plus fielded filters for sender and attachments.",
    ),
    PromptExample(
        prompt="What is on my calendar tomorrow?",
        intent_category="calendar_lookup",
        preferred_tool="calendar_list_events",
        guidance="Use an explicit tomorrow start/end window.",
    ),
    PromptExample(
        prompt="Open my Tuscany Itinerary note.",
        intent_category="notes_read",
        preferred_tool="notes_read",
        guidance="Use exact note read semantics rather than search preview output.",
    ),
)

BANNED_ROUTING_PATTERNS: tuple[str, ...] = (
    "Do not turn chronology requests into guessed keyword bundles.",
    "Do not silently choose among ambiguous named targets for writes.",
    "Do not convert latest or recent into top keyword match.",
)


def tool_contract(tool_name: str) -> ToolContract:
    return TOOL_CONTRACTS[tool_name]
