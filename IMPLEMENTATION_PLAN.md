# Apple Ecosystem MCP Server — Implementation Plan

**Author:** Abhinav Agrawal · April 2026 · v1.6  
**Status:** Corrected from v1.5 — see bottom for change log

---

## Overview

This document is a complete, Claude-executable implementation plan for an Apple Ecosystem MCP (Model Context Protocol) server. The server bridges Claude to native macOS apps — **Mail, Calendar, Contacts, Reminders, and iCloud Drive** — via AppleScript and Python, running locally on the user's Mac. It is distributed as a **Desktop Extension (`.dxt`)** for one-click installation in Claude Desktop, and published to PyPI for Claude Code users (`uvx apple-ecosystem-mcp`).

> **Scope note:** Anthropic already publishes official connectors for Apple Notes and iMessage in the registry. This server covers the five apps they don't. Together, the three packages give users complete Apple ecosystem coverage in Claude — users are directed to install the Anthropic connectors alongside this one.

Existing open-source attempts (jxnl/python-apple-mcp, pyapple-mcp, peakmojo/applescriptmcp) demonstrate feasibility but lack the polish, security handling, permissions flow, and registry packaging required for the Anthropic directory. This plan produces a production-quality implementation.

---

## Value Proposition

### The problem

Claude is already good at reasoning, drafting, and planning. What it lacks is access to the data that lives inside your Mac — your actual emails, your real calendar, the contacts you work with every day, the files you've been building up in iCloud Drive. Without that, every Claude conversation starts from zero. You paste in context manually, describe your schedule from memory, and copy-paste email threads. The gap between what Claude could do and what it actually does is the data gap.

### What this connector closes

This server gives Claude live, read-write access to your Apple productivity stack. Claude stops being a general assistant working from what you tell it and becomes a collaborator that can see your real situation and act on it directly.

The individual tools — search Mail, create a Calendar event, look up a Contact — are useful on their own. But the real value is **cross-app orchestration**: workflows that would normally require you to open four apps, copy information between them, and keep track of what you did. Claude does that coordination in a single prompt.

### Signature workflows

**Scheduling and follow-up**
> *"Find the email from the client about the proposal, check if I'm free Thursday afternoon, draft a reply with three time options, and set a reminder to follow up Friday if I haven't heard back."*

Four apps. Five steps. One sentence. Mail → Calendar → Mail → Reminders, with Claude holding the thread between all of them.

**Meeting preparation**
> *"I have a call with David Chen at 3pm. Pull up his contact details, find every email we've exchanged in the last two months, check if there's anything relevant in my iCloud Drive, and write a one-page brief I can read beforehand."*

Claude becomes a chief of staff: assembling context from Contacts, Mail, and iCloud Drive before you walk into the room.

**Account and relationship review**
> *"Find everyone at Acme Corp in my contacts, check which of them I've had meetings with this quarter, pull the latest email thread with each of them, and save a summary to iCloud Drive as acme-account-review.md."*

A task that would take 30 minutes of tab-switching takes one prompt. Contacts → Calendar → Mail → iCloud Drive, with a finished document at the end.

**Weekly planning**
> *"Look at my calendar for next week, list everything overdue in my Reminders, find any unanswered emails older than three days, and draft a prioritised plan for Monday morning."*

Claude synthesises your actual commitments and loose ends — not a generic productivity framework, but your specific situation — and hands you back a plan.

### Who this is for

**Primary users** are Mac-native professionals who haven't migrated to Google Workspace or Microsoft 365 — people who use Apple Mail, Calendar, and Reminders as their daily productivity stack. This includes freelancers, consultants, executives at smaller firms, and creative professionals. They're already invested in the Apple ecosystem and want Claude to work with it, not around it.

**Secondary users** are developers and technically curious Claude power users who want to push what Claude can do with real personal data. They'll install this early, find the edge cases, and become the loudest advocates if it works well.

**This is not for** users on Gmail, Google Calendar, or Outlook — those ecosystems have their own MCP connectors with larger user bases. This connector is specifically valuable to the segment that has stayed Apple-native.

---

## Architecture

### High-Level Design

The server runs as a local process on the user's Mac, launched by Claude Desktop via `uvx`. Claude Desktop connects over stdio. The server translates MCP tool calls into AppleScript commands that drive native macOS apps.

```
Claude Desktop
       │  MCP (stdio via uvx)
       ▼
apple-ecosystem-mcp  (Python, FastMCP ≥3.2)
       │
  ┌────┴──────────────────────────────┐
  │  AppleScript bridge               │
  │  run_applescript(script, *args)   │
  └────┬──────────────────────────────┘
       │
  ┌────┴────────────────────────────────────┐
  │  Mail · Calendar · Contacts · Reminders │
  │  iCloud Drive (~/Library/Mobile Docs)   │
  └─────────────────────────────────────────┘
```

### Technology Choices

**Python 3.11+ with FastMCP ≥3.2** is the stack. Reasons:

- FastMCP provides a decorator-based tool registration API — minimal boilerplate
- Python subprocess can call `osascript` for any macOS app
- Pure Python avoids Swift compilation complexity while still being fast enough for I/O-bound tasks
- Publishing to PyPI + `uvx` is the standard registry distribution pattern for Python MCP servers — no binary bundling required

### Transport

**stdio is the only transport needed for registry publication.** Claude Desktop launches the server as a subprocess via `uvx` and communicates over stdio. No HTTP server, no port binding.

```json
{
  "mcpServers": {
    "apple-ecosystem": {
      "command": "uvx",
      "args": ["apple-ecosystem-mcp"]
    }
  }
}
```

> **Note before coding Phase 1:** Verify the exact `mcp.run()` stdio API against [gofastmcp.com](https://gofastmcp.com) for the installed FastMCP version. FastMCP 3.x introduced breaking changes vs 2.x. Pin to `fastmcp>=3.2,<4` in `pyproject.toml`.

---

## Implementation Contracts

These contracts must be defined before Phase 1 and enforced throughout. They resolve the most common sources of brittle code in an AppleScript/Python bridge.

### Distribution Scope

This server drives macOS native apps via AppleScript — it physically cannot run on a remote server, and remote HTTP transport adds no value here. The scope is:

- **Supported**: Claude Desktop on macOS, Claude Code on macOS
- **Not supported**: Claude.ai web, Claude mobile — those clients require URL-based remote MCP. Driving Mail.app from a server in a data centre is not possible.
- **Directory listing**: Valid and encouraged. The README and directory entry must state "requires Claude Desktop on macOS." Users who find it via the directory already understand the constraint.

Phase 6 must include `"Operating System :: MacOS"` in `pyproject.toml` classifiers and a clear "Requirements: macOS 13+" section in the README.

### AppleScript → Python Serialization Protocol

All AppleScript scripts returning structured data MUST output a JSON string to stdout. Python parses it with `json.loads(result)`.

Rules:
- **Strings**: UTF-8, JSON-encoded. Never use AppleScript record syntax — it is not JSON.
- **Dates**: ISO 8601 strings. In AppleScript: `(start date of event) as «class isot» as string`
- **Null / missing value**: Output JSON `null`, not the literal `missing value`.
- **Lists**: JSON arrays built by string concatenation with a join handler.
- **Errors**: Raise `RuntimeError` from `bridge.py` — never embed errors inside the JSON payload.

Example (single record, safe for embedded user data via `as_quote()`):
```applescript
on run argv
  tell application "Mail"
    set msg to first message of inbox whose id is (item 1 of argv)
    set output to "{\"id\":\"" & id of msg & "\",\"subject\":\"" & subject of msg & "\"}"
    return output
  end tell
end run
```

### Canonical Identifier Contract

Each app exposes a different stable identifier. Use these consistently — never invent synthetic IDs.

| App | Identifier | AppleScript accessor | Stability |
|-----|-----------|---------------------|-----------|
| Mail | RFC Message-ID | `id of message` | Permanent |
| Calendar | iCalendar UID | `uid of event` | Permanent |
| Contacts | vCard UUID | `id of person` | Permanent |
| Reminders | Reminder UUID | `id of reminder` | Permanent |

**Enforcement rule**: Every list/search result MUST include the canonical ID. Every get/update/delete MUST re-fetch by that same ID. Validate the round-trip on real data before completing each phase.

### Tool Annotation Policy

FastMCP 3.x supports `readOnlyHint` and `destructiveHint` annotations per tool. Anthropic calls out missing annotations as a common rejection reason. Verify the exact annotation API at gofastmcp.com before Phase 1; apply it consistently from Phase 2 onward.

| Tool pattern | readOnlyHint | destructiveHint |
|-------------|-------------|-----------------|
| `*_search`, `*_list*`, `*_get*`, `*_find_*`, `hello_apple` | `True` | `False` |
| `*_create*`, `*_write`, `*_move`, `*_send`, `*_complete`, `*_flag*` | `False` | `False` |
| `*_update*` | `False` | `False` |
| `*_delete` | `False` | `True` |

### Localization Contract

AppleScript display names — mailbox names, calendar names, Reminders list names — are localised by macOS. "INBOX" is "Posteingang" in German, "Boîte de réception" in French. Any AppleScript that targets an object by display name will silently fail on non-English systems.

**Rules enforced in Phase 2–4:**
- **Mail**: Never hardcode mailbox names in AppleScript. Use `id of mailbox` to target mailboxes by their persistent identifier, not by name. The `mail_list_mailboxes` tool returns both `{name, id}` — callers must use the `id` for subsequent operations.
- **Calendar**: Never hardcode calendar names. Use `uid of calendar`. `calendar_list_calendars` returns `{name, uid}` — callers use the `uid`.
- **Reminders**: Reminder list names are user-defined and not localised by the OS, but they are still case-sensitive and user-specific. Accept list names as parameters (already planned) but document that they must match exactly what `reminders_lists` returns.
- **Default parameter values**: Where a default is needed (e.g., `calendar: str = None`), `None` means "all calendars" — never default to a hardcoded name like `"Calendar"`.

### Result-Size Policy

Anthropic's tool-result limit is approximately 25,000 tokens. Enforce these constraints — implement them in Phase 1 as helper constants, use them in Phases 2–5.

| Tool | Default limit | Truncation rule |
|------|--------------|-----------------|
| `mail_search` | `limit=20`, max 100 | Slice result list |
| `mail_get_thread` | plain-text body only, 8,000 chars | Strip HTML and base64 inline content before returning; append `[truncated — N chars omitted]` if still over limit; add `include_body: bool = True` |
| `calendar_list_events` | `limit=50`, max 200 | Slice result list |
| `contacts_search` | `limit=10`, max 50 | Slice result list |
| `contacts_get` | notes 2,000 chars | Truncate notes field |
| `icloud_read` | 10 MB | Refuse with `{error, size_bytes}` — already in Phase 5 |

### Concurrency and Mutation Safety

FastMCP may invoke sync tools concurrently. AppleScript against GUI apps is not safe to parallelize — concurrent `tell application "Mail"` blocks can corrupt UI state.

**Required in `bridge.py`**: module-level `threading.Lock`, acquired for every `run_applescript()` call.

**Log sanitization**: `run_applescript()` must not surface raw stderr to the caller when it contains user data. Strip the subprocess stderr before raising `RuntimeError` — replace it with a generic message that includes the AppleScript exit code but not the content. The full stderr may include email subjects, contact names, or file paths. Log it to a debug-level file logger only, never to stdout.

```python
def run_applescript(script: str, *args: str) -> str:
    with _lock:
        result = subprocess.run(...)
    if result.returncode != 0:
        # Do not pass result.stderr to the caller — it may contain user data
        raise RuntimeError(f"AppleScript failed (exit {result.returncode})")
```

**Confirmation gates** — required for high-impact tools:

| Tool | Gate | Behaviour without confirmation |
|------|------|-------------------------------|
| `mail_send` | `dry_run: bool = True` | Return `{preview: {...}, sent: False}` |
| `calendar_delete_event` | `confirm: bool = False` | Return `{preview: "Would delete: <title>", confirmed: False}` |
| `icloud_delete` | `confirm: bool = False` | Already specified — keep as-is |

---

## Tool Catalog

### Mail

| Tool Name | Apple API | Description |
|---|---|---|
| `mail_search` | Mail.app / AppleScript | Search inbox/sent by query, date range, sender |
| `mail_get_thread` | Mail.app / AppleScript | Fetch a full email thread by subject or ID |
| `mail_send` | Mail.app / AppleScript | Compose and send an email (to, cc, subject, body) |
| `mail_create_draft` | Mail.app / AppleScript | Save a draft without sending |
| `mail_list_mailboxes` | Mail.app / AppleScript | List all mailboxes/folders across all accounts, with account name and persistent ID |
| `mail_move_message` | Mail.app / AppleScript | Move message to a mailbox |
| `mail_flag_message` | Mail.app / AppleScript | Flag or unflag a message |

### Calendar

| Tool Name | Apple API | Description |
|---|---|---|
| `calendar_list_calendars` | Calendar.app / AppleScript | List all calendars across all accounts with UID, account name, and writable flag |
| `calendar_list_events` | Calendar.app / AppleScript | List events in a date range across calendars |
| `calendar_get_event` | Calendar.app / AppleScript | Get details of a specific event |
| `calendar_create_event` | Calendar.app / AppleScript | Create event with title, time, location, notes, invitees |
| `calendar_update_event` | Calendar.app / AppleScript | Update an existing event |
| `calendar_delete_event` | Calendar.app / AppleScript | Delete an event by ID |
| `calendar_find_free_time` | Calendar.app / AppleScript | Find free slots between two datetimes |

### Contacts

| Tool Name | Apple API | Description |
|---|---|---|
| `contacts_search` | Contacts.app / AppleScript | Search contacts by name, email, phone, company |
| `contacts_get` | Contacts.app / AppleScript | Get full contact record by ID |
| `contacts_create` | Contacts.app / AppleScript | Create a new contact |
| `contacts_update` | Contacts.app / AppleScript | Update fields on an existing contact |
| `contacts_list_groups` | Contacts.app / AppleScript | List contact groups |

### Reminders

| Tool Name | Apple API | Description |
|---|---|---|
| `reminders_lists` | Reminders.app / AppleScript | List all Reminders lists |
| `reminders_list` | Reminders.app / AppleScript | List reminders, optionally filtered by list or status |
| `reminders_create` | Reminders.app / AppleScript | Create a reminder with due date, notes, priority |
| `reminders_complete` | Reminders.app / AppleScript | Mark a reminder as complete |
| `reminders_delete` | Reminders.app / AppleScript | Delete a reminder |

### iCloud Drive

| Tool Name | Apple API | Description |
|---|---|---|
| `icloud_list` | `~/Library/Mobile Documents/` | List files and folders in iCloud Drive |
| `icloud_read` | Python / pathlib | Read a text or structured file |
| `icloud_write` | Python / pathlib | Write or update a file |
| `icloud_move` | Python / pathlib | Move or rename a file |
| `icloud_delete` | Python / pathlib | Delete a file (requires `confirm=True`) |
| `icloud_search` | Spotlight / `mdfind` | Search iCloud Drive by filename or content |

---

## Implementation Phases

Hand each phase to Claude Code in sequence. Each phase builds directly on the previous. Run `uv run pytest tests/ -v` after each phase before continuing.

| Phase | Name | Duration | Key Deliverables |
|---|---|---|---|
| 1 | Scaffolding & Core Server | 1–2 days | Project structure, pyproject.toml for PyPI, FastMCP stdio skeleton, AppleScript bridge with safe escaping, permissions probe on startup, `--version` flag |
| 2 | Mail Integration | 2–3 days | search, get_thread, send, create_draft, move, flag tools; attachment handling; unit tests with mock osascript |
| 3 | Calendar & Reminders | 2–3 days | Full CRUD for events; find_free_time algorithm; Reminders CRUD |
| 4 | Contacts | 1 day | Contacts search & CRUD; error handling & retries |
| 5 | iCloud Drive | 1–2 days | File listing & reading; write/move/delete with safety guards; Spotlight search; binary vs text detection |
| 6 | PyPI Publishing & Registry Submission | 1 day | Publish to PyPI via `uv publish`; verify `uvx` install works; submit to Anthropic registry |

---

## Phase 1: Scaffolding — Claude Prompt

```
# PHASE 1 PROMPT — paste into Claude Code

Install uv if not present: pip install uv

Create the project structure inside the existing apple-ecosystem-mcp directory:

  apple-ecosystem-mcp/
    pyproject.toml              # see requirements below
    README.md
    src/
      apple_ecosystem_mcp/
        __init__.py
        __main__.py             # entry point: python -m apple_ecosystem_mcp
        server.py               # FastMCP app, stdio transport
        bridge.py               # run_applescript() + as_quote() helper
        permissions.py          # probe TCC permissions at startup
        tools/
          __init__.py           # `from . import mail, calendar, contacts, reminders, icloud` — decorators must run to register tools
          mail.py               # placeholder stubs
          calendar.py
          contacts.py
          reminders.py
          icloud.py
    tests/
      conftest.py               # mock_osascript fixture
      test_bridge.py
      test_permissions.py
      test_server.py
      test_main.py
      tools/
        __init__.py             # empty
        test_mail.py            # scaffold stubs only; completed in Phase 2
        test_calendar.py        # scaffold stubs only; completed in Phase 3
        test_contacts.py        # scaffold stubs only; completed in Phase 4
        test_reminders.py       # scaffold stubs only; completed in Phase 3
        test_icloud.py          # scaffold stubs only; completed in Phase 5
      live/
        test_live_smoke.py      # opt-in only; no real Mac ops in Phase 1

pyproject.toml requirements:
  [build-system]
    requires = ["hatchling"]
    build-backend = "hatchling.build"

  [project]
    name = "apple-ecosystem-mcp"
    version = "0.1.0"
    description = "MCP server for Apple Mail, Calendar, Contacts, Reminders, and iCloud Drive"
    requires-python = ">=3.11"
    dependencies = ["fastmcp>=3.2,<4"]

  [project.scripts]
    apple-ecosystem-mcp = "apple_ecosystem_mcp.__main__:main"

  [tool.hatch.build.targets.wheel]
    packages = ["src/apple_ecosystem_mcp"]

  [dependency-groups]
    dev = ["pytest>=8", "pytest-mock>=3"]

Verify the FastMCP 3.x stdio transport API from gofastmcp.com before
writing server.py. The call is likely mcp.run() or mcp.run(transport="stdio")
but confirm exact signature.

bridge.py requirements:
  - SAFE ESCAPING PATTERN: Never use shlex for AppleScript strings.
    Use the argv pattern: build AppleScript with `on run argv` blocks
    and pass user data as positional arguments to osascript:
      subprocess.run(["osascript", "-e", script, "--", *args])
    AppleScript reads them as `item 1 of argv` — no string interpolation.
  - For scripts that cannot use argv (multi-step stateful scripts),
    provide as_quote(s: str) -> str that escapes for AppleScript string
    literal embedding: replace \ with \\, replace " with \" & quote & "
  - run_applescript(script: str, *args: str) -> str
    On non-zero exit, raise RuntimeError(f"AppleScript failed (exit {code})").
    Do NOT pass stderr to the caller — stderr may contain email subjects,
    contact names, or file paths. Log stderr at DEBUG level to a file logger
    only, never to stdout. FastMCP surfaces RuntimeError as a tool error
    automatically — do not import McpError.
  - Timeout: 30 seconds. Raise RuntimeError("AppleScript timed out") on timeout.
  - CONCURRENCY SAFETY: Add a module-level threading.Lock and acquire it
    inside run_applescript() for every subprocess.run() call:
      import threading
      _lock = threading.Lock()
      def run_applescript(...):
          with _lock:
              result = subprocess.run(...)
    AppleScript against GUI apps is not safe to parallelize.

permissions.py requirements:
  - DO NOT use tccutil — macOS only supports `tccutil reset`, not query.
  - Probe each permission with a lightweight AppleScript, catch failures:
      Automation/Mail:      tell application "Mail" to return name
      Automation/Calendar:  tell application "Calendar" to return name
      Automation/Contacts:  tell application "Contacts" to return name
      Automation/Reminders: tell application "Reminders" to return name
    Detect denial by: osascript exit code 1 AND stderr contains "-1743"
    or "not allowed to send Apple events".
  - Full Disk Access: attempt
      os.listdir(Path.home() / "Library/Mobile Documents/com~apple~CloudDocs")
    and catch PermissionError.
  - For each missing permission print:
      "⚠  Missing: [Name]"
      "   → System Settings > Privacy & Security > [Category]"
      "   → Grant access to Terminal (or apple-ecosystem-mcp after install)"
  - Server MUST start regardless — tools fail individually with clear errors.

server.py requirements:
  - Confirm FastMCP 3.x run() signature from gofastmcp.com.
  - stdio transport only (no HTTP, no port binding needed for registry).
  - Import and register all tools from tools/__init__.py.
  - Include hello_apple tool as smoke test:
      return run_applescript("return system version of (system info)")

__main__.py:
  - Define `def main() -> None:` — this is what the pyproject.toml entry point calls.
  - Parse --version flag with argparse:
      from importlib.metadata import version
      print(version("apple-ecosystem-mcp"))
  - Otherwise: call permissions.check_permissions() then server.run().

All tool stubs must have a one-line docstring — FastMCP uses it as the
MCP tool description visible to Claude.

Verify the FastMCP 3.x tool annotation API at gofastmcp.com. Apply
readOnlyHint=True to all read-only stubs (hello_apple, list/search/get
shapes) and destructiveHint=True to all delete stubs. See the Tool
Annotation Policy in Implementation Contracts for the full matrix.

tests/conftest.py:
  - mock_osascript fixture patches subprocess.run to return a
    CompletedProcess with configurable stdout/stderr/returncode.
  - timeout_error_factory fixture for subprocess.TimeoutExpired.
  - temp iCloud root fixture for future icloud_* tests.
  - monkeypatched version() and server.run() helpers for __main__ tests.

test_bridge.py tests (see docs/TEST_PLAN.md for full spec):
  - Successful call returns stdout.
  - Non-zero exit raises RuntimeError with exit code only (no stderr).
  - Timeout raises RuntimeError("AppleScript timed out").
  - subprocess.run is called with ["osascript", "-e", script, "--", *args].
  - Module-level lock serializes concurrent calls — use two threading.Thread
    instances and a threading.Event to verify blocking; no trivial no-op test.
  - as_quote() correctly escapes backslashes and double quotes.

test_permissions.py tests (see docs/TEST_PLAN.md for full spec):
  - Each app's denial is detected from exit code 1 + stderr containing -1743.
  - Full Disk Access denial detected from PermissionError on iCloud root listing.
  - Warning output includes permission name and System Settings path.
  - Permission failures do not abort startup.

test_server.py tests (see docs/TEST_PLAN.md for full spec):
  - Importing server registers all tool modules.
  - hello_apple is registered and callable.
  - Read-only stubs have readOnlyHint=True; delete stubs have destructiveHint=True.

test_main.py tests (see docs/TEST_PLAN.md for full spec):
  - --version prints semver and exits without starting server.
  - Normal startup calls check_permissions() then server.run().

tests/tools/ — create scaffold files with a single @pytest.mark.skip stub per tool.
  Each scaffold file must import the relevant tool module so import errors surface immediately.

tests/live/test_live_smoke.py — create empty file with a module-level:
  pytestmark = pytest.mark.skipif(
      not os.getenv("APPLE_MCP_LIVE_TESTS"),
      reason="Set APPLE_MCP_LIVE_TESTS=1 to run live macOS tests"
  )

Verify everything works:
  uv sync --dev                                      # install deps + dev extras
  uv run python -m apple_ecosystem_mcp --version   # prints 0.1.0
  uv run pytest tests/ -v                           # all pass

Live smoke test (requires real Mac):
  uv run python -m apple_ecosystem_mcp &
  # In Claude Desktop: "Call hello_apple" — should return macOS version string
  # Expected: no TCC permission errors for apps you've already authorised
```

---

## Phase 2: Mail — Claude Prompt

```
# PHASE 2 PROMPT — paste into Claude Code after Phase 1 is complete

Implement Mail tools in src/apple_ecosystem_mcp/tools/mail.py.

Use run_applescript() from bridge.py. Use the argv pattern for ALL
user-supplied strings — never interpolate user data into AppleScript source.

  mail_search(query: str, mailbox_id: str = None, limit: int = 20,
              since: str = None) -> list[dict]
    mailbox_id=None searches across all mailboxes in all accounts.
    Returns [{id, subject, sender, date, preview, mailbox_id, account_name}]

  mail_get_thread(message_id: str, include_body: bool = True) -> dict
    Returns: {id, subject, sender, date, body,
              attachments: [{name, size_bytes, mime_type}],
              mailbox_id, account_name}
    BODY SAFETY: Return the plain-text part only. Never return the HTML
    part or any base64-encoded inline content (embedded images, etc.) —
    these can be megabytes and will exceed the 25K token tool-result limit.
    If the message has no plain-text part, strip HTML tags from the HTML
    part as a fallback. Truncate body at 8,000 chars and append
    "[truncated — N chars omitted]" if over limit.
    include_body=False returns metadata only (no body field) — useful when
    the caller only needs subject/sender/date from a thread.

  mail_send(to: list[str], subject: str, body: str,
            cc: list[str] = None, reply_to_id: str = None,
            from_account: str = None, dry_run: bool = True) -> dict
    from_account matches account_name from mail_list_mailboxes.
    None means Mail.app default sending account.
    dry_run=True returns preview without sending; dry_run=False sends.
    Returns {success, message_id} or {preview, sent: False}.

  mail_create_draft(to: list[str], subject: str, body: str,
                    from_account: str = None) -> dict

  mail_list_mailboxes() -> list[dict]
    Returns [{name, id, account_name}] for every mailbox across all accounts.
    account_name is the display name of the Mail account (e.g. "iCloud",
    "Work Gmail"). Callers use id — not name — for all subsequent operations.

  mail_move_message(message_id: str, mailbox: str) -> dict

  mail_flag_message(message_id: str, flagged: bool) -> dict

AppleScript patterns:
  - Use `tell application "Mail"` blocks
  - Use `on run argv` for every script that takes user input
  - Handle `missing value` returns as None/empty gracefully
  - LOCALIZATION: Never target mailboxes by display name in AppleScript.
    mail_list_mailboxes must return {name, id} for each mailbox. All other
    tools that accept a mailbox parameter receive the mailbox id, not the
    name, and target it with: `mailbox id (item 1 of argv) of account ...`
  - Write tests in tests/test_mail.py using the mock_osascript fixture

Verify: uv run pytest tests/ -v

Live smoke test (requires real Mac with Mail access granted):
  # In Claude Desktop: "Search my inbox for the word 'invoice'"
  # Expected: returns a list with at least the canonical id field per result
  # "Get the thread for message ID <id from above result>"
  # Expected: returns full message with body field
```

---

## Phase 3: Calendar & Reminders — Claude Prompt

```
# PHASE 3 PROMPT

Implement Calendar and Reminders tools.

Use run_applescript() from bridge.py with the argv pattern for all
user-supplied strings.

calendar.py:

  calendar_list_calendars() -> list[dict]
    Returns [{name, uid, account_name, writable}].
    writable=False for read-only subscribed calendars and holiday calendars —
    calendar_create_event and calendar_update_event must reject non-writable
    UIDs with a clear error rather than letting AppleScript fail silently.
  calendar_list_events(start: str, end: str,
                       calendar_uid: str = None) -> list[dict]
  calendar_get_event(event_id: str) -> dict
  calendar_create_event(title: str, start: str, end: str,
                        calendar_uid: str = None,
                        location: str = None, notes: str = None,
                        invitees: list[str] = None) -> dict
    calendar_uid=None means the user's default calendar.
  calendar_update_event(event_id: str,
                        title: str = None, start: str = None,
                        end: str = None, location: str = None,
                        notes: str = None,
                        invitees: list[str] = None) -> dict
  calendar_delete_event(event_id: str) -> dict
  calendar_find_free_time(date: str, duration_minutes: int,
                          working_hours_start: int = 9,
                          working_hours_end: int = 18) -> list[dict]

reminders.py:

  reminders_lists() -> list[str]
  reminders_list(list_name: str = None,
                 completed: bool = False) -> list[dict]
  reminders_create(title: str, list_name: str = "Reminders",
                   due: str = None, notes: str = None,
                   priority: int = 0) -> dict
  reminders_complete(reminder_id: str) -> dict
  reminders_delete(reminder_id: str) -> dict

Use ISO 8601 for all datetimes. Parse with datetime.fromisoformat().
find_free_time: fetch existing events for the day, compute gaps of at
least duration_minutes within working hours, return as list of
{start, end, duration_minutes}.

LOCALIZATION: calendar_list_calendars must return {name, uid} per calendar.
All tools that filter by calendar accept calendar_uid (not name). Target in
AppleScript with: `calendar id (item 1 of argv)`. Never default to a
hardcoded calendar name — calendar_uid=None means the system default calendar.

Verify: uv run pytest tests/ -v

Live smoke test (requires real Mac with Calendar and Reminders access):
  # "List my calendars"
  # Expected: names match what you see in Calendar.app
  # "What events do I have next week?"
  # Expected: real events from your calendar, ISO dates, round-trippable UIDs
  # "Am I free Thursday at 2pm for an hour?"
  # Expected: find_free_time returns plausible slots
  # "Add a test reminder called MCP-smoke-test due tomorrow" then delete it
```

---

## Phase 4: Contacts — Claude Prompt

```
# PHASE 4 PROMPT

Implement Contacts tools in src/apple_ecosystem_mcp/tools/contacts.py.

Use run_applescript() from bridge.py with the argv pattern for all
user-supplied strings.

  contacts_search(query: str, limit: int = 10) -> list[dict]
    Search by name, email, phone, or company.
    Returns [{id, first, last, email, phone, company}]

  contacts_get(contact_id: str) -> dict
    Full record: all emails, phones, addresses, birthday, notes.

  contacts_create(first: str, last: str = None, email: str = None,
                  phone: str = None, company: str = None) -> dict
    Returns {id, success}

  contacts_update(contact_id: str,
                  first: str = None, last: str = None,
                  email: str = None, phone: str = None,
                  company: str = None) -> dict
    Returns {id, success}

  contacts_list_groups() -> list[str]

Write tests in tests/test_contacts.py using the mock_osascript fixture.

Verify: uv run pytest tests/ -v

Live smoke test (requires real Mac with Contacts access):
  # "Search my contacts for <your own name>"
  # Expected: your record returned with canonical id field
  # "Get contact details for <id from above>"
  # Expected: full record round-trips — same id, real phone/email values
```

---

## Phase 5: iCloud Drive — Claude Prompt

```
# PHASE 5 PROMPT

Implement iCloud Drive tools in src/apple_ecosystem_mcp/tools/icloud.py.

ICLOUD_ROOT = Path.home() / "Library/Mobile Documents/com~apple~CloudDocs"

IMPORTANT — path handling: user-supplied `path` values are RELATIVE to
ICLOUD_ROOT, not absolute filesystem paths. `path="/"` means the root of
iCloud Drive, not the filesystem root. Do NOT call Path(user_path).resolve()
directly — that would treat "/" as the filesystem root and fail the sandbox
check by construction.

Use this helper for every tool (implement in icloud.py):

  def _safe(user_path: str) -> Path:
      # Strip leading slash; treat as relative to ICLOUD_ROOT
      rel = Path(user_path.lstrip("/") or ".")
      if ".." in rel.parts:
          raise RuntimeError("Path escapes iCloud root")
      resolved = (ICLOUD_ROOT / rel).resolve()
      if not str(resolved).startswith(str(ICLOUD_ROOT.resolve())):
          raise RuntimeError("Path escapes iCloud root")
      return resolved

  icloud_list(path: str = "/") -> list[dict]
    Return [{name, path, size, modified, is_dir}]

  icloud_read(path: str) -> dict
    - Detect encoding with charset-normalizer; fallback to UTF-8.
    - Refuse files > 10 MB: return {error, size_bytes} without reading.
    - Return {path, content, encoding, size_bytes}

  icloud_write(path: str, content: str,
               create_dirs: bool = True) -> dict
    Write UTF-8. Create parent dirs when create_dirs=True.
    Return {path, size_bytes, success}

  icloud_move(src: str, dst: str) -> dict
    Return {src, dst, success}

  icloud_delete(path: str, confirm: bool = False) -> dict
    confirm=False: return {preview: "Would delete: <path>", confirmed: False}
    confirm=True:  delete and return {path, success}

  icloud_search(query: str, path: str = "/",
                content_search: bool = False) -> list[dict]
    Resolve path with _safe(path). Run: mdfind -onlyin <resolved> <query>
    content_search=True adds the -interpret flag.
    Reject queries containing shell metacharacters (raise RuntimeError).
    Return [{name, path, size_bytes, modified}]

Add charset-normalizer to pyproject.toml dependencies.
Write tests in tests/test_icloud.py (mock Path and subprocess).

Verify: uv run pytest tests/ -v

Live smoke test (requires Full Disk Access granted):
  # "List the root of my iCloud Drive" — path="/"
  # Expected: real file/folder names, NOT a "Path escapes iCloud root" error
  # "Write a file to iCloud Drive at test/mcp-smoke.txt with content 'hello'"
  # Expected: file appears in ~/Library/Mobile Documents/com~apple~CloudDocs/test/
  # "Read test/mcp-smoke.txt"
  # Expected: content matches
  # "Delete test/mcp-smoke.txt with confirm=True"
  # Expected: file removed; dry_run=False default still requires confirm=True
```

---

## Phase 6: Publishing & Desktop Extension Packaging — Claude Prompt

```
# PHASE 6 PROMPT

Publish the server to PyPI and package it as an Anthropic Desktop Extension (.dxt)
for one-click installation in Claude Desktop.

1. Verify the package is release-ready:
   uv run pytest tests/ -v                          # all green
   uv run python -m apple_ecosystem_mcp --version  # prints semver

2. Ensure pyproject.toml has complete PyPI metadata:
   [project]
     description = "MCP server for Apple Mail, Calendar, Contacts,
                    Reminders, and iCloud Drive — the missing half of
                    Claude's Apple ecosystem integration."
     readme = "README.md"
     license = {text = "MIT"}
     keywords = ["mcp", "apple", "macos", "mail", "calendar"]
     classifiers = [
       "Programming Language :: Python :: 3",
       "Operating System :: MacOS",
     ]
     urls.Homepage = "https://github.com/<user>/apple-ecosystem-mcp"
     urls.Repository = "https://github.com/<user>/apple-ecosystem-mcp"

3. Build and publish to PyPI:
   uv build
   uv publish          # requires PyPI API token in UV_PUBLISH_TOKEN

4. Verify uvx install works from a clean shell (no venv active):
   uvx apple-ecosystem-mcp --version    # should print version from PyPI

5. Create the Desktop Extension bundle (.dxt):
   A .dxt file is a ZIP archive containing manifest.json. It enables
   one-click installation in Claude Desktop without requiring the user
   to edit JSON config files or use Terminal.

   Create manifest.json at the repo root:
   {
     "dxt_version": "0.1",
     "name": "apple-ecosystem-mcp",
     "display_name": "Apple Ecosystem",
     "version": "<same semver as pyproject.toml>",
     "description": "MCP server for Apple Mail, Calendar, Contacts, Reminders, and iCloud Drive.",
     "author": { "name": "<your name>" },
     "server": {
       "type": "python",
       "mcp_config": {
         "command": "uvx",
         "args": ["apple-ecosystem-mcp"]
       }
     },
     "compatibility": {
       "platforms": ["darwin"],
       "claude_desktop": ">=0.10"
     },
     "privacy_policy_url": "<URL>",
     "homepage_url": "https://github.com/<user>/apple-ecosystem-mcp"
   }

   Bundle it:
   zip -j apple-ecosystem-mcp.dxt manifest.json

   Test: Double-click apple-ecosystem-mcp.dxt — Claude Desktop should
   prompt the user to install the extension. After install, ask Claude:
   "Call hello_apple."

6. Update README with:
   - Primary install: "Download apple-ecosystem-mcp.dxt and double-click
     to install in Claude Desktop" (link to GitHub releases)
   - Secondary install (Claude Code): the uvx claude_desktop_config.json snippet
   - Full tool catalog table
   - macOS permissions setup: step-by-step System Settings instructions
   - Troubleshooting: TCC error -1743, Full Disk Access, osascript timeout
   - "Complete Apple Setup" section pointing users to Anthropic's official
     Apple Notes and iMessage connectors
   - Privacy policy URL and Terms of Service URL
   - Clear statement: "Requires Claude Desktop on macOS 13+"

7. GitHub Release:
   - Tag the release with the semver (e.g. git tag v1.0.0)
   - Attach apple-ecosystem-mcp.dxt to the GitHub release assets
   - Users download and double-click — no Terminal required
```

---

## Permissions & Security Notes

macOS requires explicit user approval (TCC — Transparency, Consent, Control) for each app category. The server probes for permissions on startup and prints actionable instructions for any that are missing.

### Required macOS Permissions

| Permission | System Settings Path | Tools That Need It |
|---|---|---|
| Automation → Mail | Privacy & Security → Automation | All `mail_*` tools |
| Automation → Calendar | Privacy & Security → Automation | All `calendar_*` tools |
| Automation → Contacts | Privacy & Security → Automation | All `contacts_*` tools |
| Automation → Reminders | Privacy & Security → Automation | All `reminders_*` tools |
| Full Disk Access | Privacy & Security → Full Disk Access | All `icloud_*` tools |

### Security Invariants (enforced in code)

- All iCloud paths are `resolve()`d and sandboxed to `ICLOUD_ROOT` before any file operation
- All user strings passed to AppleScript use the `on run argv` pattern — no string interpolation
- `icloud_delete` requires `confirm=True` to actually delete
- `icloud_search` rejects queries containing shell metacharacters
- No credentials stored — server delegates entirely to macOS keychain via native apps
- Server runs stdio only — no network port opened

---

## Quick Start (Development)

```bash
cd apple-ecosystem-mcp
pip install uv                              # once
uv sync --dev
uv run pytest tests/ -v                    # run tests
uv run python -m apple_ecosystem_mcp --version
```

**Add to Claude Desktop for local development** (before publishing to PyPI):

```json
{
  "mcpServers": {
    "apple-ecosystem": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/apple-ecosystem-mcp",
               "apple-ecosystem-mcp"]
    }
  }
}
```

**After PyPI publish:**

```json
{
  "mcpServers": {
    "apple-ecosystem": {
      "command": "uvx",
      "args": ["apple-ecosystem-mcp"]
    }
  }
}
```

---

## Distribution & Publishing Checklist

**Correctness**
- [ ] `uv run pytest tests/ -v` passes with no failures
- [ ] Per-phase live smoke tests passed on real Mac data (not just mocks)
- [ ] `uvx apple-ecosystem-mcp --version` prints a clean semver string
- [ ] Package is live on PyPI and `uvx apple-ecosystem-mcp` installs cleanly
- [ ] Claude Desktop integration tested end-to-end (`hello_apple` responds)
- [ ] Tested on macOS 14 Sonoma and macOS 15 Sequoia

**Tool quality**
- [ ] All tools have clear, accurate one-line MCP docstrings
- [ ] All tools have correct `readOnlyHint` / `destructiveHint` annotations per the Tool Annotation Policy
- [ ] `mail_send` requires `dry_run=False` to actually send; default is `dry_run=True`
- [ ] `calendar_delete_event` requires `confirm=True` to actually delete
- [ ] `icloud_delete` requires `confirm=True` to actually delete
- [ ] No `**kwargs` in any tool signature — all optional params are explicit
- [ ] No hardcoded display names (mailbox names, calendar names) in AppleScript — all use persistent IDs/UIDs
- [ ] AppleScript errors are sanitized before surfacing — no user data (email subjects, contact names) in RuntimeError messages

**Security and safety**
- [ ] No hardcoded credentials or API keys anywhere in code
- [ ] All iCloud paths validated through `_safe()` helper — path traversal not possible
- [ ] `icloud_search` rejects shell metacharacters in query string
- [ ] All user strings pass through argv pattern or `as_quote()` — no AppleScript injection

**Desktop Extension requirements**
- [ ] README states "requires Claude Desktop on macOS 13+" clearly
- [ ] README includes privacy policy URL and terms of service URL
- [ ] README includes "Complete Apple Setup" pointer to Anthropic's Notes and iMessage connectors
- [ ] `pyproject.toml` classifiers include `"Operating System :: MacOS"`
- [ ] `manifest.json` present at repo root with correct `dxt_version`, `server.mcp_config`, and `compatibility.platforms: ["darwin"]`
- [ ] `apple-ecosystem-mcp.dxt` builds without error (`zip -j apple-ecosystem-mcp.dxt manifest.json`)
- [ ] `.dxt` double-click installs in Claude Desktop and `hello_apple` responds
- [ ] `.dxt` attached to GitHub release assets
- [ ] `uvx apple-ecosystem-mcp --version` works from a clean shell (Claude Code path)

---

## Change Log

### v1.0 → v1.1 (corrections to original PDF plan)

| # | Issue | Change |
|---|---|---|
| 1 | Project named `apple-mcp` throughout | Renamed to `apple-ecosystem-mcp` / `apple_ecosystem_mcp` everywhere |
| 2 | `tccutil query` does not exist on macOS | Replaced with lightweight AppleScript probes catching error `-1743` |
| 3 | `shlex` used for AppleScript string escaping — wrong and insecure | Replaced with `on run argv` pattern; added `as_quote()` for edge cases |
| 4 | FastMCP version unspecified; API may differ in v3.x | Pinned to `fastmcp>=3.2,<4`; added note to verify transport API from docs |
| 5 | `pyobjc-framework-EventKit` listed as dep but unused | Removed from dependencies |
| 6 | Python 3.13 needs PyInstaller ≥6.0 | N/A — PyInstaller dropped in v1.2 |
| 7 | `--version` flag in submission checklist but missing from Phase 1 | Added `--version` to Phase 1 scaffolding prompt |
| 8 | `messages_search` via AppleScript broken on macOS 12+ | N/A — Messages dropped in v1.2 |
| 9 | 127.0.0.1 binding only in security notes, not in Phase 1 | N/A — HTTP transport dropped in v1.2 |
| 10 | `McpError` import path unspecified | Changed to `raise RuntimeError` — FastMCP surfaces it automatically |

### v1.2 → v1.3 (execution safety and FastMCP compatibility)

| # | Issue | Change |
|---|---|---|
| 16 | Distribution goal ("directory-ready") implied web/mobile support | Scoped to Claude Desktop + Code on macOS; README must state requirement explicitly |
| 17 | Tool annotations missing — documented registry rejection reason | Added Tool Annotation Policy table; Phase 1 prompt requires annotations on all stubs |
| 18 | `calendar_update_event` and `contacts_update` used `**kwargs` — won't register in FastMCP | Replaced with explicit optional parameters in Phase 3 and Phase 4 prompts |
| 19 | iCloud path bug: `Path("/").resolve()` = filesystem root, not iCloud root | Replaced with `_safe(user_path)` helper that strips leading slash and joins relative to ICLOUD_ROOT |
| 20 | No canonical identifier contract for Mail, Calendar, Contacts, Reminders | Added Identifier Contract table specifying stable ID per app |
| 21 | No serialization protocol between AppleScript and Python | Added Serialization Protocol requiring JSON output from all structured AppleScript |
| 22 | No result-size controls; 25K token limit not enforced | Added Result-Size Policy table with per-tool limits and truncation rules |
| 23 | AppleScript calls not serialized — concurrent calls unsafe against GUI apps | Added `threading.Lock` requirement in Phase 1 bridge.py spec |
| 24 | Only `icloud_delete` had a confirmation gate | Added `dry_run=True` to `mail_send`; `confirm=False` to `calendar_delete_event` |
| 25 | Testing relied entirely on mocked `osascript` | Added live smoke test block at end of every phase prompt |
| 26 | AppleScript stderr may contain user data (emails, contacts) logged to output | `run_applescript()` now strips stderr from RuntimeError message; DEBUG-only file logging |
| 27 | Mailbox/calendar names are localised — hardcoded names break on non-English macOS | Localization Contract added; mailboxes use persistent `id`, calendars use `uid`; no default display-name strings; `calendar_uid` replaces `calendar` parameter |

### v1.5 → v1.6 (Desktop Extension packaging)

| # | Issue | Change |
|---|---|---|
| 32 | Phase 6 targeted Connectors Directory (remote OAuth SaaS); local MCP servers distribute via Desktop Extensions | Overview updated; Phase 6 rewritten for `.dxt` packaging + GitHub release |
| 33 | Submission checklist had Connectors Directory requirements | Replaced with Desktop Extension checklist (`manifest.json`, `.dxt` build, double-click install test) |
| 34 | `osascript` subprocess approach challenged as "fatally slow" | Rejected: 100–500ms per call is acceptable for interactive use; proven by existing Apple MCP projects |
| 35 | TCC failures with unsigned PyInstaller binary | Non-issue: `.dxt` + Claude Desktop as host handles TCC; PyInstaller already removed in v1.2 |

### v1.4 → v1.5 (multi-account Mail and calendar write-safety)

| # | Issue | Change |
|---|---|---|
| 28 | `mail_list_mailboxes` returned names only — no account context, no persistent ID | Returns `{name, id, account_name}`; all callers use `id` not name |
| 29 | `mail_search` defaulted to "INBOX" — breaks for users with multiple accounts | Default changed to `mailbox_id=None` (all mailboxes); results include `account_name` |
| 30 | `mail_send` had no way to choose sending account | Added `from_account: str = None` parameter matching `account_name` from `mail_list_mailboxes` |
| 31 | `calendar_list_calendars` returned name/uid only — no account context, no write guard | Returns `{name, uid, account_name, writable}`; create/update tools must reject `writable=False` UIDs |

### v1.1 → v1.2 (scope and distribution model)

| # | Issue | Change |
|---|---|---|
| 11 | Notes and iMessage included despite Anthropic having official connectors | Removed Notes and Messages from scope entirely; README will point users to Anthropic connectors |
| 12 | Phase 6 built PyInstaller binary + Homebrew formula | Replaced with PyPI publish via `uv publish` + `uvx` invocation — standard registry pattern |
| 13 | HTTP transport included for "Cowork/remote" use case | Dropped — stdio via `uvx` is the only transport needed for registry publication |
| 14 | venv-based development setup | Replaced with `uv sync` / `uv run` throughout |
| 15 | Phase 4 included Notes and Messages | Phase 4 now covers Contacts only |
