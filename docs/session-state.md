# Session State — Apple Ecosystem MCP

Updated automatically at end of each session. Tracks progress across days.

## Current Status
- **Last changed:** 2026-06-10
- **Current version:** v0.6.0 (GitHub MCPB release)
- **Next TODO:** Live-test the installed v0.6.0 MCPB in Claude Desktop with real Mail and Notes data, then continue the separate Mail rework plan for true chronological inbox queries.

## Session Log

### Session 7 (2026-06-28, MCPB installability, Node compatibility, and permission UX release)
- **What changed:**
  - Reworked the primary MCPB to run through a Node launcher for current Claude Desktop compatibility while keeping the existing Python tool engine and bundled native helper.
  - Added separate Node and future UV manifests/build targets, stricter MCPB validation, package metadata, and GitHub-profile author metadata for Anthropic submission readiness.
  - Embedded macOS privacy usage descriptions in the native helper and added a local menu-bar companion app skeleton for service status and permission workflows.
  - Hardened Contacts and Reminders fallback behavior when native framework access is denied or unavailable.
  - Fixed a live Contacts lookup regression where the AppleScript fallback failed to compile after native Contacts permission denial.
  - Pulled the latest GitHub README screenshot commits before release preparation.
- **Verification:**
  - Focused packaging tests: `tests/test_packaging.py`.
  - Focused Contacts/Reminders/native tests during triage.
  - Release build validation via `scripts/validate_mcpb.py --mode node`.
- **Blockers:**
  - Track C native companion UX is still a skeleton/control-plane start, not a polished bundled app install experience.
- **Next steps:**
  - Install the v1.1.0 MCPB in Claude Desktop and smoke-test `hello_apple`, `apple_inventory`, Contacts, Reminders, Calendar, Mail, and Notes.
  - Decide whether to fully rewrite the server in Node.js if Anthropic interprets "built with Node.js" as implementation language rather than MCPB runtime.

### Session 6 (2026-06-10, mail metadata provider and Notes reliability release)
- **What changed:**
  - Added a local Mail metadata provider backed by Apple Mail's read-only Envelope Index for metadata/date-window searches, with provider selection and degraded-mode fallback behavior.
  - Added unit coverage for the Mail store path plus provider routing in `mail_search`.
  - Fixed `notes_read` so Notes plain-text extraction is the canonical read path again, avoiding large rich-note HTML timeouts.
  - Kept the Apple Notes SQLite `NoteStore` path as a read-only degraded fallback after AppleScript failure/timeout only.
  - Removed the stale tracked `.claude/worktrees/vibrant-proskuriakova-efe262` gitlink during repo cleanup.
  - Rebuilt the MCPB artifact for v0.6.0.
- **Verification:**
  - Focused non-live tests: `99 passed` via `UV_CACHE_DIR=.uv-cache uv run pytest tests/tools/test_mail.py tests/test_mail_store.py tests/tools/test_notes.py tests/test_server.py -q`
- **Blockers:**
  - Mail still does not support a true "received after timestamp" inbox query for message bodies or full-fidelity recency views; that remains separate follow-on work.
- **Next steps:**
  - Validate installed behavior against real `notes_read`, `mail_search` date windows, and scheduled workflows that depend on those reads.
  - Continue the dedicated Mail redesign plan for true chronological and mailbox-first queries.

### Session 5 (2026-06-08, practical-use, scheduling, and timeout hardening)
- **What changed:**
  - Added local preferences, aliases, stable target resolution, and Apple inventory tools so Claude can speak in friendly names while tools act on stable identities.
  - Added scheduled task config, safety policy, CLI/launchd wiring, MCP scheduled-task tools, and read-only report workflows.
  - Hardened inventory behavior so `apple_inventory` degrades per scope instead of failing entirely when one Apple app errors.
  - Added argument-aware inventory caching with defensive copies and test cache isolation.
  - Added per-tool AppleScript timeout plumbing and scan budgets for broad Mail and Reminders queries to reduce live timeouts.
  - Rebuilt the MCPB artifact for v0.4.0.
- **Verification:**
  - Non-live test suite: `296 passed, 8 warnings`.
- **Blockers:**
  - Live AppleScript behavior still depends on real app data volume and macOS Automation permissions; installed MCPB needs manual smoke testing after release.
- **Next steps:**
  - Install the v0.4.0 MCPB in Claude Desktop.
  - Test `apple_inventory`, `mail_search`, `reminders_list`, `calendar_list_events`, and `contacts_search` against real data.
  - If live timeouts remain, add per-app diagnostics that report elapsed time and scope without surfacing private data.

### Session 4 (2026-06-08, post-release runtime hardening)
- **What changed:**
  - Fixed Calendar AppleScript runtime issues: date parsing now uses month constants correctly, and calendar name is used as the stable local identifier because `uid of calendar` is unsupported.
  - Fixed Reminders runtime behavior: permission errors are standardized, no-filter `reminders_list` avoids timeout behavior, and AppleScript JSON escaping uses ASCII character codes for control characters.
  - Fixed Contacts search fallback by moving match logic inline inside the `tell application "Contacts"` block so person properties are read in the proper AppleScript context.
  - Updated local manifest runner args for local development.
  - Simplified future releases to one GitHub-hosted MCPB artifact and removed the separate package publishing path.
  - Replaced stale Node-style Makefile commands with Python/MCPB commands.
  - Fixed MCPB launch args to use `${__dirname}/server/runner.py` so Claude Desktop resolves the bundled runner path.
  - Analyzed Claude Desktop logs and fixed Contacts search AppleScript compilation plus Mail search timeout/malformed-JSON behavior.
  - Verified non-live tests: `222 passed, 8 warnings`.
- **Blockers:** None in unit/non-live coverage. Live macOS AppleScript behavior still needs manual testing against real Calendar, Reminders, and Contacts data.
- **Next steps:**
  - Push the six local commits currently ahead of `origin/main`.
  - Re-test in the target client/runtime, especially Contacts search, Calendar list/get events, and Reminders list/list-all behavior.
  - Decide whether the next implementation work should be backlog tests (`TST-001`/`TST-002`/`TST-003`) or packaging diagnostics (`PKG-003`).

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
  - Remaining low-priority items: packaging diagnostics and TST-001/002/003 (regression/contract tests).

### Session 2 (2026-04-23, post-release)
- **What changed:**
  - Finalized specs and tests for Reminders after intentional implementation design change (list_name=None delegation, ISO date normalization).
  - Updated IMPLEMENTATION_PLAN.md, docs/TEST_PLAN.md, and test_reminders.py to reflect correct contracts.
  - Version bump 0.1.3 → 0.1.4: patch release for spec/test alignment and improved documentation.
- **Blockers:** None blocking v0.1.4 release.
- **Next steps:**
  - Pick backlog item: `MAIL-001` (canonical RFC Message-ID), `CAL-001` (event overlap), `TST-001` (regression), or `PKG-001` (desktop bundle stability).

### Session 1 (2026-04-23)
- **What changed:**
  - Hardened AppleScript interactions and JSON escaping across Mail/Calendar/Contacts/Reminders.
  - Fixed Reminders create/list targeting and ISO due-date normalization.
  - Fixed Calendar ISO parsing (month mapping) and record property setting for create/update.
  - Improved Mail search scanning; added `internal_id` and prefer RFC `message id` where available.
  - Made bridge logging resilient in read-only CWD environments (Claude Desktop / MCPB).
  - Added a trackable backlog: `docs/FEATURE_TODOS.md`.
- **Blockers:**
  - Live AppleScript behavior varies by account/mailbox volume and macOS privacy settings; needs targeted regression tests.
  - Desktop bundle install/update behavior needs live validation after packaging changes.
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
