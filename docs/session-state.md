# Session State — Apple Ecosystem MCP

Updated automatically at end of each session. Tracks progress across days.

## Current Status
- **Last changed:** 2026-04-23
- **Current version:** v0.1.4 (PyPI + GitHub released)
- **Next TODO:** Pick from high-value backlog: `MAIL-001` or `CAL-001` or `TST-001`

## Session Log

### Session 2 (2026-04-23, post-release)
- **What changed:**
  - Finalized specs and tests for Reminders after intentional implementation design change (list_name=None delegation, ISO date normalization).
  - Updated IMPLEMENTATION_PLAN.md, docs/TEST_PLAN.md, and test_reminders.py to reflect correct contracts.
  - Version bump 0.1.3 → 0.1.4: patch release for spec/test alignment and improved documentation.
- **Blockers:** None blocking v0.1.4 release.
- **Next steps:**
  - Pick backlog item: `MAIL-001` (canonical RFC Message-ID), `CAL-001` (event overlap), `TST-001` (regression), or `PKG-001` (DXT stability).

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
