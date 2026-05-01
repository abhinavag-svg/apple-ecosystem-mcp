# Session State — Apple Ecosystem MCP

Updated automatically at end of each session. Tracks progress across days.

## Current Status
- **Last changed:** 2026-05-01
- **Current version:** v0.3.0 (PyPI + GitHub released)
- **Next TODO:** Remaining features: `PKG-002`, `PKG-003`, `TST-001`, `TST-002`, `TST-003`

## Session Log

### Session 3 (2026-05-01, v0.3.0 feature release)
- **What changed:**
  - Completed all high-value feature TODOs: MAIL-001-006, CAL-001-004, CON-001-003, REM-001-003, ICLD-001-003, PKG-001 (21/26 items).
  - Mail: Smart mailbox hierarchy, attachment metadata (`{name, size_bytes, mime_type}`), and date filtering (`since`/`before` ISO).
  - Calendar: Event overlap logic, clearable fields, attendee management with timezone handling.
  - Contacts: Native predicate search with fallback, structured email/phone access, group membership filtering.
  - Reminders: List targeting by stable ID, permission error standardization, metadata (recurrence/tags/priority).
  - iCloud: Deterministic filename search with bounded os.walk, binary-safe base64 read/write, stat/mkdir helpers.
  - All subsystems tested: 64 mail tests, 47 iCloud tests, 22 reminders tests pass.
  - Version bump: 0.2.1 → 0.3.0, manifest.json and pyproject.toml aligned.
- **Blockers:** None; all tests passing.
- **Next steps:**
  - Remaining low-priority items: PKG-002/003 (DXT cache busting, diagnostics), TST-001/002/003 (regression/contract tests).

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
