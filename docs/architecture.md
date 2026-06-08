# Architecture — Apple Ecosystem MCP

## Overview

Apple Ecosystem MCP is a local Python MCP server for Claude Desktop. It exposes tools for Apple Mail, Calendar, Contacts, Reminders, and iCloud Drive, and executes native macOS automation through AppleScript.

```text
Claude Desktop
    |
    | MCP over stdio
    v
FastMCP server
    |
    | Python tool handlers
    v
AppleScript bridge / filesystem helpers
    |
    v
Mail, Calendar, Contacts, Reminders, iCloud Drive
```

## Runtime

- `src/apple_ecosystem_mcp/server.py` creates the FastMCP server and registers tools.
- `src/apple_ecosystem_mcp/tools/` contains the app-specific tool modules.
- `src/apple_ecosystem_mcp/bridge.py` runs AppleScript through `osascript`.
- `src/apple_ecosystem_mcp/permissions.py` checks common macOS permission gaps at startup.
- `server/runner.py` is the MCPB bundle entrypoint. It runs the bundled source with `uv run --project`.

The server runs locally. It does not host an HTTP service or store credentials.

## Distribution

The project ships as a GitHub Release asset:

```text
apple-ecosystem-mcp.mcpb
```

The MCPB contains:

- `manifest.json`
- `server/runner.py`
- `src/apple_ecosystem_mcp/`
- `pyproject.toml`
- `uv.lock`
- `README.md`
- `LICENSE`
- `logo.svg`

Claude Desktop launches the bundle entrypoint. The runner uses the bundled source tree, so the project itself does not require a separate package publishing step.

## Safety Constraints

- User data is passed to AppleScript as positional arguments, never interpolated into AppleScript source.
- AppleScript calls are serialized with a module-level lock because GUI scripting is not thread-safe.
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
