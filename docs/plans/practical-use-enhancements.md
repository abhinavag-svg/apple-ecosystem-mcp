# Practical Use Enhancements

## Summary

This plan tracks V1 work for making the Apple Ecosystem MCP connectors practical for everyday use. The product thesis is:

> Claude speaks in friendly names; tools operate on stable identities.

Users should be able to say "my work calendar", "Archive", "personal reminders", or "receipts" naturally. The tools should resolve those phrases to stable Apple containers before acting, and should ask for clarification instead of guessing when names are ambiguous.

## Scope

- Add local preferences for defaults and aliases.
- Add a shared resolver for friendly names, stable IDs, and ambiguity handling.
- Normalize container inventory metadata across Mail, Calendar, Reminders, Contacts, and iCloud Drive.
- Update write paths so stable IDs are preferred over display names.
- Preserve backward compatibility where practical, but make ambiguity explicit for write actions.

## Public Interfaces

Add these MCP tools:

- `apple_inventory`
- `apple_preferences_get`
- `apple_preferences_set_default`
- `apple_preferences_add_alias`
- `apple_preferences_remove_alias`
- `apple_resolve_target`

## Parallel Workstreams

| Agent | Model | Ownership | Task |
|---|---:|---|---|
| A1 Resolver/Preferences | `gpt-5.4` medium | New preferences/resolver modules + tests | Implement local config storage, target schema, alias/default CRUD, resolution behavior, ambiguity errors. |
| A2 Container Inventory | `gpt-5.4-mini` medium | Discovery output normalization in Mail/Calendar/Reminders/Contacts/iCloud | Add consistent metadata fields where available: `id`, `name`, `kind`, `account_name`, `path`, `writable`, `default_candidate`. |
| A3 MCP Preference Tools | `gpt-5.4-mini` medium | Server tool registration + preference tool wrappers | Add `apple_inventory`, preference CRUD tools, and target resolution tool. |
| A4 Write Tool Integration | `gpt-5.4` medium | Existing write tools only | Route friendly-name target inputs through resolver, prefer stable IDs, return structured ambiguity/writable errors. |
| A5 Docs/Contracts | `gpt-5.4-mini` low | README/docs/test plan only | Document the friendly-name/stable-identity contract, examples, and workflow expectations. |

## Dependency Order

1. Start A1 and A2 in parallel.
2. Start A3 after A1 schema exists.
3. Start A4 after A1 and relevant A2 output shapes are known.
4. Start A5 after public interface names are stable.
5. Parent agent integrates results, resolves conflicts, and runs targeted tests.

## Targeted Tests

Run the new resolver/preference/server tests:

```bash
uv run pytest tests/test_preferences.py tests/test_resolver.py tests/test_server.py -q
```

Run only connector suites touched by the implementation:

```bash
uv run pytest tests/tools/test_mail.py -q
uv run pytest tests/tools/test_calendar.py -q
uv run pytest tests/tools/test_reminders.py -q
uv run pytest tests/tools/test_contacts.py -q
uv run pytest tests/tools/test_icloud.py -q
```

Run the full suite only if targeted failures suggest shared registration, schema, or bridge behavior has regressed.

## Acceptance Criteria

- Duplicate names never silently resolve for write actions.
- Defaults and aliases persist locally outside the repo.
- Write tools prefer stable identities.
- Friendly names remain usable through resolver behavior.
- Ambiguous targets return structured errors.
- Read-only targets return structured errors for write attempts.
- Existing compatible tool calls continue to work where practical.

## Notes For Implementation

- Preferences should be local-only and telemetry-free.
- Do not store raw private data in preferences.
- If a stable Apple ID is unavailable, expose the most stable local identifier already proven by the connector and document the limitation.
- This version is a prerequisite for scheduled tasks because scheduled workflows need reliable target resolution.
