# Apple Ecosystem MCP Server — Test Plan

This document is a non-implementation test specification derived from [IMPLEMENTATION_PLAN.md](/Users/abhinav/projects/git/apple-ecosystem-mcp/IMPLEMENTATION_PLAN.md). Its purpose is to define test coverage, safety checks, and the future pytest layout for the Apple Ecosystem MCP server without creating executable tests yet.

The goal is to make implementation straightforward later: another engineer should be able to create the actual pytest files directly from this spec, phase by phase.

## Test Structure

Status: Documentation-only spec

Planned project layout, matching the Phase 1 structure and later subsystem phases:

```text
apple-ecosystem-mcp/
  IMPLEMENTATION_PLAN.md
  docs/
    TEST_PLAN.md
  tests/
    conftest.py
    test_bridge.py
    test_permissions.py
    test_server.py
    test_main.py
    tools/
      test_mail.py
      test_calendar.py
      test_contacts.py
      test_reminders.py
      test_icloud.py
    live/
      test_live_smoke.py
```

Execution intent by area:

- `tests/conftest.py`: Executable in Phase 1
- `tests/test_bridge.py`: Executable in Phase 1
- `tests/test_permissions.py`: Executable in Phase 1
- `tests/test_server.py`: Executable in Phase 1
- `tests/test_main.py`: Executable in Phase 1
- `tests/tools/test_mail.py`: Scaffold in Phase 1, complete in Phase 2
- `tests/tools/test_calendar.py`: Scaffold in Phase 1, complete in Phase 3
- `tests/tools/test_contacts.py`: Scaffold in Phase 1, complete in Phase 4
- `tests/tools/test_reminders.py`: Scaffold in Phase 1, complete in Phase 3
- `tests/tools/test_icloud.py`: Scaffold in Phase 1, complete in Phase 5
- `tests/live/test_live_smoke.py`: Live/manual validation

## Core Infrastructure Tests

### `tests/conftest.py`

Phase when executable: Phase 1

Test intent:

- centralize shared fixtures for mocked `subprocess.run`
- provide reusable success, timeout, permission-denied, and generic-failure subprocess outputs
- provide reusable temp-path helpers for future filesystem tests
- provide fixtures for server startup and CLI entry-point patching

Concrete test support fixtures to define later:

- `mock_osascript` fixture for patching `subprocess.run`
- `completed_process_factory` for stdout/stderr/returncode combinations
- `timeout_error_factory` for `subprocess.TimeoutExpired`
- temp iCloud root fixture for `icloud_*` tests
- monkeypatched `version()` and `server.run()` helpers for `__main__` tests

### `tests/test_bridge.py`

Phase when executable: Phase 1

Test intent:

- verify `run_applescript()` handles subprocess interaction safely
- verify AppleScript input is passed via argv rather than interpolation
- verify error sanitization does not leak user data
- verify concurrency protection is present
- verify `as_quote()` escapes embedded strings for the limited cases where interpolation is unavoidable

Concrete test cases:

- successful AppleScript execution returns stdout
- non-zero subprocess exit raises `RuntimeError` with exit code only
- raised error does not include raw stderr content such as subjects, names, or file paths
- timeout raises `RuntimeError("AppleScript timed out")`
- `subprocess.run()` is called with `["osascript", "-e", script, "--", *args]`
- all user-supplied strings are forwarded as positional argv items
- module-level lock serializes concurrent calls to `run_applescript()` — implementation note: use two `threading.Thread` instances and a `threading.Event` to verify the second call blocks while the first holds the lock; a trivially-passing no-op test is not acceptable here
- `as_quote()` escapes backslashes correctly
- `as_quote()` escapes embedded double quotes correctly

### `tests/test_permissions.py`

Phase when executable: Phase 1

Test intent:

- verify startup permission probing detects missing macOS permissions accurately
- verify the server warns clearly without aborting startup

Concrete test cases:

- Mail permission denial is detected from exit code `1` and stderr containing `-1743`
- Calendar permission denial is detected from exit code `1` and stderr containing `-1743`
- Contacts permission denial is detected from exit code `1` and stderr containing `-1743`
- Reminders permission denial is detected from exit code `1` and stderr containing `-1743`
- Apple events denial is detected from stderr containing `not allowed to send Apple events`
- Full Disk Access failure is detected from `PermissionError` on iCloud root listing
- warning output includes missing permission name
- warning output includes the expected System Settings path
- permission failures do not prevent the process from continuing

### `tests/test_server.py`

Phase when executable: Phase 1

Test intent:

- verify the FastMCP server object is wired correctly
- verify tool-registration side effects happen from `tools/__init__.py`
- verify the smoke-test tool and annotations match the implementation contracts

Concrete test cases:

- importing the server registers all placeholder tool modules
- `hello_apple` is registered and callable
- `hello_apple` delegates to `run_applescript("return system version of (system info)")`
- read-only stubs are marked with `readOnlyHint=True`
- delete stubs are marked with `destructiveHint=True`
- no tool definition uses unsupported `**kwargs` in a way that would break FastMCP schema registration

### `tests/test_main.py`

Phase when executable: Phase 1

Test intent:

- verify CLI entry-point behavior
- verify `--version` and normal startup flow are both correct

Concrete test cases:

- `python -m apple_ecosystem_mcp --version` prints a clean semver string
- `main()` exits after printing version without starting the server
- normal startup calls `permissions.check_permissions()`
- normal startup calls `server.run()` after permission checks
- permission warnings do not block `server.run()`

## Mail Tests

Target file path: `tests/tools/test_mail.py`

Phase when executable: Scaffold in Phase 1, complete in Phase 2

Test intent:

- validate Mail tool payload shapes, safety gates, localization rules, and result-size policy

Concrete test cases:

- `mail_list_mailboxes()` returns mailbox `name`, canonical `id`, and `account_name`
- mailbox targeting uses mailbox ID rather than localized display name
- `mail_search()` with `mailbox_id=None` searches across all accounts
- `mail_search()` enforces default `limit=20`
- `mail_search()` caps results at max 100
- `mail_search()` returns records with `id`, `subject`, `sender`, `date`, `preview`, `mailbox_id`, and `account_name`
- `mail_get_thread()` returns canonical message ID and mailbox/account metadata
- `mail_get_thread(include_body=False)` omits body content and returns metadata only
- `mail_get_thread()` returns plain-text body only
- HTML fallback is stripped to text if plain text is absent
- inline base64 or HTML-heavy content is excluded from result payloads
- body content is truncated at 8,000 characters with truncation marker
- attachment metadata includes `name`, `size_bytes`, and `mime_type`
- `mail_send(dry_run=True)` returns preview payload and `sent=False`
- `mail_send(dry_run=False)` performs send path only after confirmation intent is explicit
- `mail_create_draft()` creates draft metadata without sending
- `mail_move_message()` re-fetches and moves by canonical message ID
- `mail_flag_message()` toggles flagged state by canonical message ID
- `mail_delete()` deletes by canonical message ID
- `mail_delete()` is marked `destructiveHint=True`
- `mail_send()` with a valid `from_account` routes through the specified account
- `mail_send()` with an unrecognised `from_account` returns a clear error before attempting send
- missing Mail permission surfaces a clear tool-level error

## Calendar Tests

Target file path: `tests/tools/test_calendar.py`

Phase when executable: Scaffold in Phase 1, complete in Phase 3

Test intent:

- validate Calendar tool schemas, UID-based targeting, mutation gates, and free-time logic

Concrete test cases:

- `calendar_list_calendars()` returns `name`, `uid`, `account_name`, and `writable`
- calendar targeting uses UID rather than localized display name
- `calendar_list_events()` accepts ISO 8601 date inputs
- `calendar_list_events()` enforces default limit and max-result cap from the result-size policy
- `calendar_list_events()` returns canonical event IDs and calendar metadata
- `calendar_get_event()` re-fetches by canonical event ID
- `calendar_create_event()` with `calendar_uid=None` does not default to a hardcoded display name such as `"Calendar"`
- `calendar_create_event()` accepts optional location, notes, and invitees
- `calendar_update_event()` uses explicit optional parameters, not unsupported `**kwargs`
- `calendar_delete_event(confirm=False)` returns preview payload and does not delete
- `calendar_delete_event(confirm=True)` performs the delete path
- `calendar_find_free_time()` computes gaps within working hours only
- `calendar_find_free_time()` ignores events outside the requested day window
- overlapping events are merged correctly before gap calculation
- malformed datetime input returns a clear validation error
- missing Calendar permission surfaces a clear tool-level error

## Contacts Tests

Target file path: `tests/tools/test_contacts.py`

Phase when executable: Scaffold in Phase 1, complete in Phase 4

Test intent:

- validate Contacts lookup, canonical IDs, field normalization, and explicit update semantics

Concrete test cases:

- `contacts_search()` searches by name, email, phone, or company
- `contacts_search()` returns `id`, `first`, `last`, `email`, `phone`, and `company`
- `contacts_search()` enforces default `limit=10`
- `contacts_search()` caps results at max 50
- `contacts_get()` re-fetches by canonical contact ID
- `contacts_get()` returns all emails, phones, addresses, birthday, and notes
- long notes are truncated to 2,000 characters
- `missing value` fields are normalized to `None` or empty collections
- `contacts_create()` returns canonical contact ID and success status
- `contacts_update()` uses explicit optional fields rather than unsupported `**kwargs`
- `contacts_list_groups()` returns user-visible group names
- missing Contacts permission surfaces a clear tool-level error

## Reminders Tests

Target file path: `tests/tools/test_reminders.py`

Phase when executable: Scaffold in Phase 1, complete in Phase 3

Test intent:

- validate Reminders list handling, exact-list-name rules, filtering, and mutation behavior

Concrete test cases:

- `reminders_lists()` returns exact user list names
- `reminders_list()` filters by list name when provided
- `reminders_list()` filters by completion status
- list names are treated as exact user-provided names, not localized defaults
- `reminders_create()` accepts optional due date, notes, and priority
- due date parsing accepts valid ISO 8601 values
- invalid due date input returns a clear validation error
- `reminders_complete()` marks reminder complete by canonical reminder ID
- `reminders_delete()` deletes by canonical reminder ID
- `missing value` fields are normalized cleanly
- missing Reminders permission surfaces a clear tool-level error

## iCloud Drive Tests

Target file path: `tests/tools/test_icloud.py`

Phase when executable: Scaffold in Phase 1, complete in Phase 5

Test intent:

- validate filesystem safety boundaries, path normalization, size limits, and safe search behavior

Concrete test cases:

- user paths are normalized relative to `ICLOUD_ROOT`, not treated as filesystem-root absolute paths
- `icloud_list("/")` resolves to the iCloud root and succeeds
- path traversal attempts outside `ICLOUD_ROOT` are rejected
- symlink or resolved-path escapes are rejected
- `icloud_read()` refuses files larger than 10 MB with `{error, size_bytes}`
- `icloud_read()` returns `path`, `content`, `encoding`, and `size_bytes` for valid text files
- text decoding falls back safely when encoding detection is uncertain
- binary-like content is not returned as plain text without detection
- `icloud_write()` writes UTF-8 content and creates parent directories when `create_dirs=True`
- `icloud_move()` renames or moves within the iCloud root only
- `icloud_delete(confirm=False)` returns preview payload and does not delete
- `icloud_delete(confirm=True)` deletes only after explicit confirmation
- `icloud_search()` invokes `mdfind` safely without shell interpolation
- unsafe search queries are rejected before subprocess execution
- missing Full Disk Access surfaces a clear tool-level error

## Live macOS Smoke Tests

Target file path: `tests/live/test_live_smoke.py`

Phase when executable: Live/manual validation

Test intent:

- provide optional real-machine validation on macOS with actual TCC permissions and app data
- verify the local AppleScript bridge works outside pure mocking

Concrete test cases:

- `hello_apple` returns the macOS version string
- Mail smoke test exercises one read-only Mail tool if Mail permission is granted
- Calendar smoke test exercises one read-only Calendar tool if Calendar permission is granted
- Contacts smoke test exercises one read-only Contacts tool if Contacts permission is granted
- Reminders smoke test exercises one read-only Reminders tool if Reminders permission is granted
- iCloud smoke test exercises one read-only iCloud tool if Full Disk Access is granted
- skipped tests clearly explain missing permissions or local-environment requirements

Execution rules for the eventual implementation:

- skip by default unless an explicit env var enables live tests
- avoid destructive live operations
- keep fixtures and sample queries minimal and privacy-preserving

## Coverage Rules and Safety Invariants

Phase when executable: Begins in Phase 1 and expands through Phase 5

Test intent:

- enforce the cross-cutting contracts defined in `IMPLEMENTATION_PLAN.md`
- keep the suite focused on behavior, safety, and compatibility rather than brittle implementation snapshots

Concrete rules to verify later:

- all structured AppleScript outputs are JSON strings parseable by Python
- every list/search result includes the canonical ID for the subsystem
- every get/update/delete operation re-fetches by canonical ID
- read-only tools are marked with `readOnlyHint=True`
- destructive tools are marked with `destructiveHint=True`
- no FastMCP tool uses unsupported signature patterns that prevent schema generation
- result-size policy is enforced across Mail, Calendar, Contacts, and iCloud tools
- high-impact actions require explicit confirmation or dry-run behavior
- localized names are not used as internal identifiers for Mail or Calendar targeting
- tool errors remain sanitized and do not leak raw stderr or sensitive user data
- live tests remain optional and do not block standard local development

## Assumptions

- This spec is documentation-only and does not create any files under `src/` or `tests/`.
- `docs/TEST_PLAN.md` is the default home for the testing spec.
- The future implementation should prefer contract-style assertions over brittle AppleScript string snapshots.
- The future executable suite should be runnable with mocked subprocess behavior by default, with live macOS validation kept opt-in.
