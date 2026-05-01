# High-Value TODOs (Trackable)

This is a product-focused backlog of the most valuable next improvements for `apple-ecosystem-mcp`.

Legend:
- **P0**: blocking reliability/safety issue
- **P1**: high user value (next)
- **P2**: nice-to-have / performance / polish

## Mail

- [x] **MAIL-001 (P0)** `mail_search` canonical IDs: always return RFC `message_id` and use it consistently in `mail_get_thread`/move/flag/delete.
- [x] **MAIL-002 (P1)** `mail_search` advanced filters: `from`, `to`, `cc`, `unread`, `flagged`, `has_attachments`, `account_name`, `mailbox_ids[]`.
- [x] **MAIL-003 (P1)** `mail_search` body search (opt-in): `search_fields=["subject","sender","body"]` with explicit perf caps and clear truncation indicator.
- [ ] **MAIL-004 (P1)** Smart Mailboxes + mailbox hierarchy: include mailbox path/type so users can target “Inbox” vs rules-based mailboxes reliably.
- [ ] **MAIL-005 (P2)** Attachments metadata in search results: `{name,size_bytes,mime_type}` (capped) and `has_attachments` boolean.
- [ ] **MAIL-006 (P2)** Date filtering: accept `since`/`before` ISO inputs and filter via proper date comparisons (not lexicographic strings).

## Calendar

- [x] **CAL-001 (P0)** Event overlap logic: `calendar_list_events` must include events that overlap the window (start < end_window AND end > start_window).
- [x] **CAL-002 (P1)** Clearable fields: support explicit `clear_location`, `clear_notes` in `calendar_update_event`.
- [x] **CAL-003 (P1)** Attendees: expose attendees in list/get and support updating attendees without duplicates.
- [x] **CAL-004 (P2)** Timezone strategy: define contract for inputs with offsets/Z and normalize to local for AppleScript.

## Reminders

- [x] **REM-001 (P0)** List targeting: add `reminders_list_id` or stable list identifier (names are localized and not unique).
- [x] **REM-002 (P1)** Better error surfacing: map “not authorized / -1743” to a standardized permission error message for tool calls.
- [x] **REM-003 (P2)** Recurrence + tags + priorities: include more metadata where available (keep payload small).

## Contacts

- [x] **CON-001 (P1)** Fast search: prefer native predicate search where safe; fall back to scanning only when predicates error.
- [x] **CON-002 (P1)** Structured fields: return labeled emails/phones (not just “first email/phone”).
- [x] **CON-003 (P2)** Group membership: include groups for a contact and allow filtering search by group.

## iCloud Drive

- [x] **ICLD-001 (P1)** Deterministic filename search: implement bounded `os.walk` filename search (with caps) to avoid Spotlight false negatives.
- [x] **ICLD-002 (P1)** Binary-safe read/write: support base64 for non-UTF8 files (`encoding="base64"` option).
- [x] **ICLD-003 (P2)** `icloud_stat` + `icloud_mkdir`: explicit metadata/mkdir helpers to reduce caller guesswork.

## Packaging / DX / Ops

- [x] **PKG-001 (P0)** DXT bootstrap stability: ensure Claude Desktop runs in read-only CWD; all temp/log writes must use writable dirs.
- [ ] **PKG-002 (P1)** Cache busting: pin `uvx` invocation to package version in the DXT manifest and document upgrade steps.
- [ ] **PKG-003 (P2)** Telemetry-free diagnostics: add opt-in debug logging and a “collect diagnostics” tool (no PII).

## Test Coverage

- [ ] **TST-001 (P0)** Add regression tests for AppleScript record-building bugs (props `& {}` patterns) across Calendar/Reminders.
- [ ] **TST-002 (P1)** Add unit tests for Mail JSON escaping (newlines/tabs) to prevent malformed JSON regressions.
- [ ] **TST-003 (P2)** Add contract tests for tool schemas (annotations, no varargs/kwargs, required args).
