# Apple Ecosystem MCP — Implementation Guide

An MCP server that bridges Claude to native macOS apps (Mail, Calendar, Contacts, Reminders, iCloud Drive) via AppleScript and Python. Distributed as a `.dxt` Desktop Extension + PyPI package.

## Critical Contracts (All Agents Must Follow)

These are non-negotiable. Breaking them causes tool registration failures, permission errors, or security vulnerabilities.

### AppleScript Bridge
- **argv pattern only:** Always pass user data as positional arguments: `osascript -e 'on run argv...end run' -- "$arg1" "$arg2"`
- **Never interpolate:** Do not use `shlex` or string interpolation into AppleScript source
- **Serialization:** All structured returns must be JSON strings, parsed with `json.loads()`
- **Dates:** ISO 8601 format via `«class isot» as string` in AppleScript
- **Threading:** Module-level `threading.Lock` serializes every `subprocess.run()` call — AppleScript against GUI is not thread-safe

### Canonical Identifiers
- **Mail:** RFC Message-ID (`id of message` in AppleScript)
- **Calendar:** iCalendar UID (`uid of event`)
- **Contacts:** vCard UUID (`id of person`)
- **Reminders:** UUID (`id of reminder`)
- All tools must target by ID/UID, never by localized display name

### Localization Rule
- Mailbox/calendar/list names ARE locale-specific (English, French, etc. have different names)
- Never hardcode display names like `"Calendar"`, `"INBOX"`, `"Reminders"`
- Always use persistent IDs or return `{name, id, account_name}` so callers use `id` not `name`
- Defaults: `calendar_uid=None` means "all calendars"; `mailbox_id=None` means "all mailboxes"

### Error Handling
- **Never leak stderr:** `stderr` may contain email subjects, contact names, file paths
- Raise `RuntimeError(f"AppleScript failed (exit {code})")` only; log stderr to DEBUG file logger
- FastMCP surfaces `RuntimeError` as tool error automatically — don't import `McpError`

### Result-Size Policy (per tool)
| Tool | Limit | Enforcement |
|---|---|---|
| mail_search | 20 default, 100 max | Slice list before returning |
| mail_get_thread | 8,000 chars | Strip HTML/base64 inline, truncate, append `[truncated — N chars omitted]` |
| calendar_list_events | 50 default, 200 max | Slice list |
| contacts_search | 10 default, 50 max | Slice list |
| contacts_get.notes | 2,000 chars | Truncate |
| icloud_read | 10 MB | Refuse with `{error, size_bytes}` |

### Tool Annotations
- `readOnlyHint=True`: All `*_search`, `*_list`, `*_get` tools
- `destructiveHint=True`: All `*_delete` tools
- All others: defaults (read-write, non-destructive)

### Confirmation Gates
- `mail_send(dry_run: bool = True)` — default is dry-run; must be `False` to send
- `calendar_delete_event(confirm: bool = False)` — default is no-op; must be `True` to delete
- `icloud_delete(confirm: bool = False)` — default is no-op; must be `True` to delete

### Path Safety (iCloud only)
- User paths are relative to `ICLOUD_ROOT` (typically `~/Library/Mobile Documents/com~apple~CloudDocs`)
- Always use `_safe(user_path)` helper: strip leading slash, join relative to root, resolve, verify no escape
- Reject `..` segments and symlink escapes before any file operation

## Project Structure

```
apple-ecosystem-mcp/
  IMPLEMENTATION_PLAN.md         # Phase-by-phase implementation specs
  docs/
    TEST_PLAN.md                 # Test contracts per subsystem
  src/
    apple_ecosystem_mcp/
      __init__.py
      __main__.py                # Entry point: --version flag + permissions check
      server.py                  # FastMCP app, stdio transport
      bridge.py                  # run_applescript(), as_quote(), threading.Lock
      permissions.py             # TCC probe at startup, print warnings
      tools/
        __init__.py              # `from . import mail, calendar, ...` (decorators must run)
        mail.py                  # Phase 2
        calendar.py              # Phase 3
        contacts.py              # Phase 4
        reminders.py             # Phase 3
        icloud.py                # Phase 5
  tests/
    conftest.py                  # mock_osascript, timeout fixtures
    test_bridge.py               # Phase 1
    test_permissions.py          # Phase 1
    test_server.py               # Phase 1
    test_main.py                 # Phase 1
    tools/
      __init__.py
      test_mail.py               # Scaffold in Phase 1, complete in Phase 2
      test_calendar.py           # Scaffold in Phase 1, complete in Phase 3
      test_contacts.py           # Scaffold in Phase 1, complete in Phase 4
      test_reminders.py          # Scaffold in Phase 1, complete in Phase 3
      test_icloud.py             # Scaffold in Phase 1, complete in Phase 5
    live/
      test_live_smoke.py         # Opt-in via APPLE_MCP_LIVE_TESTS=1
  .claude/
    settings.local.json          # Pre-approved tools, agent teams enabled
  CLAUDE.md                       # This file
```

## Phase Breakdown & Responsibilities

| Phase | Owner | Deliverable | Dependencies |
|-------|-------|-------------|--------------|
| 1 | Single session (you) | Scaffold, bridge.py, permissions.py, server.py, hello_apple, core tests | None |
| 2 | Mail Engineer | mail.py tools (8 tools), mail tests complete | Phase 1 |
| 3 | Calendar Engineer | calendar.py tools (6 tools), calendar tests complete | Phase 1 |
| 4 | Contacts Engineer | contacts.py + reminders.py tools (7 tools total), tests complete | Phase 1 |
| 5 | Single session | icloud.py tools (5 tools), iCloud tests complete | Phase 1 |
| 6 | Single session | manifest.json, .dxt bundling, GitHub release, PyPI publish | Phases 2–5 |

## How to Use This Document

**Phase 1 (solo):** Read IMPLEMENTATION_PLAN.md Phase 1 prompt. This CLAUDE.md is your reference for contracts.

**Phases 2–4 (agent teams):** Each agent reads:
1. IMPLEMENTATION_PLAN.md (full document)
2. docs/TEST_PLAN.md (their subsystem's test spec)
3. CLAUDE.md (this file — contracts only)
4. Their phase prompt from IMPLEMENTATION_PLAN.md

**Agent Communication:**
- Task list: `~/.claude/tasks/apple-mcp-team/`
- Messaging: "Message the Mail Engineer about..." (use agent names)
- Blockers: message team lead immediately with full context

## Git Workflow

```bash
# Phase 1: develop on main
uv sync --dev
uv run pytest tests/ -v
git add -A && git commit -m "feat: phase 1 scaffold + bridge + permissions"
git push origin main

# Phases 2–4: agents develop on feature branches
git checkout -b phase-2-mail   # Mail Engineer
# ... implement mail.py ...
uv run pytest tests/tools/test_mail.py -v
git commit -m "feat: phase 2 mail tools"
# Message team lead: "Ready for review"

# Phase 5–6: back to single session
git checkout main && git pull   # Merge phases 2–4 first
# ... implement icloud.py ...
# ... create manifest.json, .dxt ...
```

## Running Tests

```bash
# Phase 1: core tests only
uv run pytest tests/test_bridge.py tests/test_permissions.py tests/test_server.py tests/test_main.py -v

# During phase 2: mail + core tests
uv run pytest tests/ -k "not live" -v

# Full suite (phases 2–5):
uv run pytest tests/ -k "not live" -v

# Live macOS smoke tests (optional, requires real permissions):
APPLE_MCP_LIVE_TESTS=1 uv run pytest tests/live/ -v
```

## Key Decision: Why These Contracts?

- **argv pattern:** Prevents AppleScript injection. One safe pattern avoids maintenance burden of two patterns.
- **threading.Lock:** AppleScript drives GUI apps; concurrent calls crash or produce inconsistent state.
- **Canonical IDs not names:** Localization breaks hardcoded names. IDs persist across language changes.
- **Result-size limits:** 25K token Anthropic limit forces truncation; better to be explicit than surprise Claude with "body too large."
- **Confirmation gates:** Prevent accidental mass deletions; `dry_run=True` default is safer than `confirm=True` default.
- **Error sanitization:** Stderr contains user data (email subjects, file names); never surface it to Claude.

## Resources

- **[IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md)** — Full implementation specs, phase prompts, tool contracts
- **[docs/TEST_PLAN.md](./docs/TEST_PLAN.md)** — Test specs, coverage matrix, safety checks
- **[.claude/settings.local.json](./.claude/settings.local.json)** — Pre-approved tools, agent teams enabled
