# Architecture — Apple Ecosystem MCP

## Overview

Apple Ecosystem MCP is a local Python MCP server for Claude Desktop. It exposes tools for Apple Mail, Calendar, Contacts, Reminders, Notes, and iCloud Drive. Calendar, Contacts, and Reminders use a bundled native macOS helper by default; Mail and Notes use AppleScript; iCloud Drive uses local filesystem and Spotlight APIs.

```text
Claude Desktop
    |
    | MCP over stdio
    v
FastMCP server
    |
    | Python tool handlers
    v
Provider layer / native helper / AppleScript bridge / filesystem helpers
    |
    v
Mail, Calendar, Contacts, Reminders, Notes, iCloud Drive
```

## Runtime

- `src/apple_ecosystem_mcp/server.py` creates the FastMCP server and registers tools.
- `src/apple_ecosystem_mcp/tools/` contains the app-specific tool modules.
- `src/apple_ecosystem_mcp/native_provider.py` invokes the bundled native helper for Calendar, Contacts, and Reminders.
- `native/apple-ecosystem-helper.swift` is compiled into `bin/apple-ecosystem-helper` inside the MCPB.
- `src/apple_ecosystem_mcp/bridge.py` runs AppleScript through `osascript` for Mail, Notes, and legacy fallback paths.
- `src/apple_ecosystem_mcp/permissions.py` checks common macOS permission gaps at startup.
- `server/runner.py` is the MCPB bundle entrypoint. The manifest launches it with `${__dirname}/server/runner.py`, and the runner executes the bundled source with `uv run --project`.
- Set `APPLE_ECOSYSTEM_MCP_PROVIDER=applescript` to force the legacy AppleScript provider for Calendar, Contacts, and Reminders.

The server runs locally. It does not host an HTTP service or store credentials.

## Distribution

The project ships as a GitHub Release asset:

```text
apple-ecosystem-mcp.mcpb
```

The MCPB contains:

- `manifest.json`
- `server/runner.py`
- `bin/apple-ecosystem-helper`
- `src/apple_ecosystem_mcp/`
- `pyproject.toml`
- `uv.lock`
- `README.md`
- `LICENSE`
- `logo.svg`

Claude Desktop launches the bundle entrypoint. The runner uses the bundled source tree, so the project itself does not require a separate package publishing step.

## Safety Constraints

- User data is passed to the native helper over JSON stdin/stdout, and to AppleScript as positional arguments where AppleScript is still used.
- AppleScript calls are serialized with a module-level lock because GUI scripting is not thread-safe; native helper calls use bounded subprocess timeouts.
- Tool results are bounded and truncated where needed.
- Destructive tools require explicit confirmation arguments.
- iCloud paths are resolved relative to the iCloud root and checked for path traversal.
- AppleScript stderr is not surfaced directly to Claude because it may contain private data.

## Testing

```bash
make test
```

Live tests are opt-in and require a real macOS account with permissions granted:

```bash
APPLE_MCP_LIVE_TESTS=1 uv run pytest tests/live/ -v
```
