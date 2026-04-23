# Session State — Apple Ecosystem MCP

Updated automatically at end of each session. Tracks progress across days.

## Current Status
- **Last changed:** 2026-04-23
- **Next TODO:** Start `MAIL-001` (canonical message IDs end-to-end)

## Session Log

### Session 1 (2026-04-23)
- **What changed:**
  - Hardened AppleScript interactions and JSON escaping across Mail/Calendar/Contacts/Reminders.
  - Fixed Reminders create/list targeting and ISO due-date normalization.
  - Fixed Calendar ISO parsing (month mapping) and record property setting for create/update.
  - Improved Mail search scanning; added `internal_id` and prefer RFC `message id` where available.
  - Made bridge logging resilient in read-only CWD environments (Claude Desktop / DXT).
  - Added a trackable backlog: `docs/FEATURE_TODOS.md`.
- **Blockers:**
  - Live AppleScript behavior varies by account/mailbox volume and macOS privacy settings; needs targeted regression tests.
  - DXT/uvx cache can pin old PyPI builds without explicit version pinning.
- **Next steps:**
  - Implement `MAIL-001` to make RFC `message_id` canonical everywhere (search/get/move/flag/delete).
  - Add regression tests `TST-001` and `TST-002`.

---

## How to Update

At end of session, run daily handoff ritual:
```bash
!gca "feat: describe what you did"
"Update docs/session-state.md with what changed today and what's next."
```

This keeps CLAUDE.md lean while preserving session history.
