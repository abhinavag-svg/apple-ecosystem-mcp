# V3 Native Provider And Near-Term Practical Features

## Summary

Finish the reliability layer for Calendar, Reminders, and Contacts by routing them through a bundled Swift helper, then add practical Tuesday-afternoon workflows that do not require a Mail rewrite. Mail remains unchanged in this plan.

## Product Thesis

Claude should speak in friendly names, but tools should operate on stable identities. Reliability comes from native APIs where available, bounded result sets, explicit confirmation for destructive actions, and boringly predictable workflow tools.

## Scope

- Native Calendar, Reminders, and Contacts provider through `apple-ecosystem-helper`.
- Python provider wrapper with structured errors and AppleScript fallback during migration.
- Calendar workflow helpers for today, tomorrow, week, date-specific lookup, search, and all-day creation.
- Reminders workflow helpers for due-today, overdue, search, update, rename, and list CRUD.
- Contacts workflow helpers for delete and birthday review.
- Initial Notes connector using AppleScript, scoped to account/folder/list/search/read/create/append/delete.
- Documentation and targeted unit coverage.

## Out Of Scope

- Mail search/indexing rework.
- iMessage support.
- Cloud service or hosted backend.
- Removing AppleScript fallback for Calendar, Reminders, and Contacts before live validation.

## Implementation Workstreams

| Agent | Model | Ownership | Task |
|---|---:|---|---|
| V3-A Native Helper | `gpt-5.4` medium | Swift helper | Implement EventKit and Contacts.framework operations for Calendar, Reminders, and Contacts with JSON stdin/stdout envelopes. |
| V3-B Provider Routing | `gpt-5.4` medium | Python provider layer | Centralize helper invocation, timeout handling, fallback behavior, and structured errors. |
| V3-C Workflow Tools | `gpt-5.4-mini` medium | Calendar/Reminders/Contacts wrappers | Add practical helper tools that compose existing native operations without changing public schemas unexpectedly. |
| V3-D Notes Connector | `gpt-5.4-mini` medium | Notes tool module | Add a bounded AppleScript-backed Notes connector with stable IDs where Notes exposes them. |
| V3-E Docs/Tests/Packaging | `gpt-5.4-mini` low | README, architecture, tests, MCPB | Document backend ownership, add mocked unit tests, compile helper into local MCPB. |

## Cost And Tool Controls

- Use focused `rg`/`sed` inspection and targeted tests.
- Use fake helper and monkeypatched provider responses for non-live tests.
- Avoid live macOS tests unless explicitly requested.
- Do not run the whole release process until local MCPB validation passes.

## Acceptance Criteria

- Local MCPB includes `bin/apple-ecosystem-helper`.
- Calendar, Reminders, and Contacts default to native provider when helper is available.
- Existing MCP tool names remain stable.
- New workflow tools have read-only or destructive annotations as appropriate.
- Notes is available as a pragmatic first pass, clearly documented as AppleScript-backed.
- Focused non-live tests pass.

## Follow-Up

- After local validation, commit and release V3.
- Then begin the standalone Mail rework plan.
