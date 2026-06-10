# Implementation Log

This is an append-only tracking file for implementation milestones and future blog-post material. Update it at major milestones, not after every small edit.

## Template

```md
## YYYY-MM-DD - Workstream Name

- Agent/model:
- Ownership:
- Files touched:
- Tests run:
- Result:
- Cost/token optimization:
- Notes for blog:
```

## 2026-06-08 - V1 Practical Use Enhancements

- Agent/model: A1 `gpt-5.4` medium, A2 `gpt-5.4-mini` medium, A3 `gpt-5.4-mini` medium, A4 `gpt-5.4` medium
- Ownership: resolver/preferences, container inventory normalization, MCP preference tools, write-tool target resolution
- Files touched: preferences/resolver modules, preference MCP tools, Mail/Calendar/Reminders/Contacts/iCloud discovery and write-path tests
- Tests run: `env UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/test_preferences.py tests/test_resolver.py tests/test_server.py tests/test_preference_tools.py tests/tools/test_mail.py tests/tools/test_calendar.py tests/tools/test_reminders.py tests/tools/test_contacts.py tests/tools/test_icloud.py -q`
- Result: 226 passed
- Cost/token optimization: used `gpt-5.4` only for resolver and safety-sensitive write paths; used `gpt-5.4-mini` for normalized metadata and MCP wrappers
- Notes for blog: parallelized the stable-identity layer by separating core resolution, inventory metadata, wrapper tools, and write-path integration

## 2026-06-08 - V2 Scheduled Task Capabilities

- Agent/model: B1 `gpt-5.4` medium, B2 `gpt-5.4` medium, B3 `gpt-5.4-mini` medium, B4 `gpt-5.4-mini` medium
- Ownership: scheduler config/registry, read-only workflow runner, CLI plus launchd, scheduled-task MCP tools
- Files touched: scheduled task storage, runner, CLI, MCP wrappers, scheduler tests
- Tests run: `env UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/test_scheduled_tasks.py tests/test_scheduler_cli.py tests/test_scheduler_safety.py tests/test_scheduler_runner.py tests/tools/test_scheduled_tasks.py tests/test_server.py tests/test_main.py -q`
- Result: 49 passed
- Cost/token optimization: used `gpt-5.4` for config validation and workflow orchestration; used `gpt-5.4-mini` for CLI and MCP wrapper surfaces
- Notes for blog: kept scheduled tasks adjacent to MCP rather than turning the MCP server into a daemon; final integration added `schedule run <name>` while preserving launchd all-enabled execution

## 2026-06-08 - Integrated Targeted Verification

- Agent/model: parent integrator
- Ownership: final scoped verification across touched runtime surfaces
- Files touched: none
- Tests run: `env UV_CACHE_DIR=/private/tmp/uv-cache uv run pytest tests/test_preferences.py tests/test_resolver.py tests/test_preference_tools.py tests/test_scheduled_tasks.py tests/test_scheduler_cli.py tests/test_scheduler_safety.py tests/test_scheduler_runner.py tests/test_server.py tests/test_main.py tests/tools/test_mail.py tests/tools/test_calendar.py tests/tools/test_reminders.py tests/tools/test_contacts.py tests/tools/test_icloud.py tests/tools/test_scheduled_tasks.py -q`
- Result: 271 passed
- Cost/token optimization: skipped live macOS tests and full-suite repetition; covered all changed modules and directly affected connector suites
- Notes for blog: targeted verification was enough because the changed surface was limited to new modules, tool registration, connector discovery outputs, and selected write paths

## 2026-06-10 - V3 Native Provider And Near-Term Features

- Agent/model: V3-A/V3-B `gpt-5.4` medium, V3-C/V3-D/V3-E `gpt-5.4-mini` medium/low
- Ownership: Swift native helper, Python provider routing, Calendar/Reminders/Contacts workflow tools, initial Notes connector, docs/tests/packaging
- Files touched: `native/apple-ecosystem-helper.swift`, `src/apple_ecosystem_mcp/native_provider.py`, Calendar/Reminders/Contacts/Notes tools, README/architecture docs, targeted connector tests
- Tests run: `uv run pytest tests/test_native_provider.py tests/test_server.py tests/tools/test_calendar.py tests/tools/test_reminders.py tests/tools/test_contacts.py tests/tools/test_notes.py -q`; `uv run pytest tests/ -k "not live" -q`; `make build`
- Result: Swift helper compiled; 123 focused tests passed; 328 non-live tests passed with 8 existing warnings; local MCPB built at `mcpb/apple-ecosystem-mcp.mcpb`
- Cost/token optimization: kept Mail rewrite out of this batch, used mocked provider responses for unit tests, and limited verification to native provider plus touched connector surfaces
- Notes for blog: this split keeps reliability work behind stable MCP tool names while moving slow AppleScript paths to native APIs where Apple frameworks exist
