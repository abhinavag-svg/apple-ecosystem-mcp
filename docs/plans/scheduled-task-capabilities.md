# Scheduled Task Capabilities

## Summary

This plan tracks V2 work for adding local scheduled workflows. The product thesis is:

> Scheduled tasks are a local automation layer adjacent to MCP, not magic background MCP behavior.

The MCP server remains reactive. Scheduling is handled by a local CLI plus macOS `launchd`, with MCP tools for conversational setup and manual runs.

## Scope

- Add local scheduled task config and registry.
- Add a workflow runner for safe report-producing tasks.
- Add CLI commands for schedule management.
- Add dry-run-testable `launchd` plist generation.
- Add MCP wrappers for listing, creating, running, enabling, and disabling scheduled tasks.
- Add a safety policy that blocks destructive scheduled actions in V1.

## Public Interfaces

Add these CLI commands:

- `apple-ecosystem-mcp schedule list`
- `apple-ecosystem-mcp schedule run <name>`
- `apple-ecosystem-mcp schedule install <name>`
- `apple-ecosystem-mcp schedule uninstall <name>`

Add these MCP tools:

- `scheduled_tasks_list`
- `scheduled_tasks_get`
- `scheduled_tasks_create`
- `scheduled_tasks_run`
- `scheduled_tasks_enable`
- `scheduled_tasks_disable`

## Parallel Workstreams

| Agent | Model | Ownership | Task |
|---|---:|---|---|
| B1 Scheduler Config/Registry | `gpt-5.4` medium | New scheduled-task config modules + tests | Define task config schema, storage, enable/disable state, validation, and task registry. |
| B2 Workflow Runner | `gpt-5.4` medium | New workflow execution module | Implement read-only workflows: daily briefing, tomorrow preview, overdue reminders review, unread priority mail review, receipt finder, weekly planning digest. |
| B3 CLI + launchd | `gpt-5.4-mini` medium | CLI commands + plist generation | Add schedule list/run/install/uninstall commands and dry-run-testable `launchd` plist generation. |
| B4 MCP Scheduled Tools | `gpt-5.4-mini` medium | Scheduled task MCP wrappers | Add MCP tools for listing, creating, running, enabling, and disabling scheduled tasks. |
| B5 Safety/Docs | `gpt-5.4-mini` low | Safety policy tests + docs | Document and test scheduled-task safety rules: read-only by default, destructive actions blocked. |

## Dependency Order

1. Start B1 first.
2. Start B2 and B3 after B1 config shape is fixed.
3. Start B4 after B1 APIs exist.
4. Start B5 after safety policy names are stable.
5. Parent agent integrates results, reviews safety behavior, and runs targeted tests.

## Targeted Tests

Run new scheduler tests:

```bash
uv run pytest tests/test_scheduled_tasks.py tests/test_scheduler_cli.py tests/test_scheduler_safety.py -q
```

If workflow code touches connector behavior, add only the relevant connector suites:

```bash
uv run pytest tests/tools/test_calendar.py tests/tools/test_reminders.py tests/tools/test_mail.py tests/tools/test_icloud.py -q
```

Run live tests only when intentionally validating real macOS behavior:

```bash
APPLE_MCP_LIVE_TESTS=1 uv run pytest tests/live/ -q
```

## Acceptance Criteria

- Scheduled tasks run locally.
- Scheduling uses CLI plus `launchd`.
- V1 scheduled tasks are read-only or report-producing.
- Destructive scheduled actions are blocked.
- Manual task runs work through CLI and MCP.
- Missing or ambiguous resolver targets fail safely with clear configuration errors.
- Logs contain task metadata only, not private content.

## Notes For Implementation

- This version depends on the practical-use resolver and preferences layer.
- Do not keep the MCP server alive as a scheduler daemon.
- Default outputs should be local Markdown reports or another inspectable local artifact.
- Scheduled sends, deletes, file deletion, and calendar mutation are out of scope for the first scheduled-task release.
