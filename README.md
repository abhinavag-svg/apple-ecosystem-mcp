# Apple Ecosystem MCP

An MCP server that bridges Claude to native macOS apps (Mail, Calendar, Contacts, Reminders, iCloud Drive) via AppleScript and Python.

**Requirements:** macOS 13+ with Claude Desktop or Claude Code

## Installation

Download the `.dxt` file from [GitHub Releases](https://github.com/abhinavagrawal/apple-ecosystem-mcp/releases) and double-click to install in Claude Desktop.

Or via `uvx` for Claude Code:

```bash
uvx apple-ecosystem-mcp
```

## macOS Permissions

The server requires explicit user approval for each app category. When you first run the server, you'll see warnings for any missing permissions. Follow the System Settings instructions to grant access.

- **Automation** → Mail, Calendar, Contacts, Reminders
- **Full Disk Access** (for iCloud Drive)

## Tools

The server provides tools for:
- **Mail**: search, read, send, move, flag, delete messages across multiple accounts
- **Calendar**: list, create, update, delete events; find free time
- **Contacts**: search, read, create, update contacts and groups
- **Reminders**: list, create, complete, delete reminders across multiple lists
- **iCloud Drive**: read, write, move, delete files; search by metadata

See [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) for the complete tool catalog and specifications.

## Complete Apple Setup

This server covers Mail, Calendar, Contacts, Reminders, and iCloud Drive. For complete Apple ecosystem coverage in Claude, also install Anthropic's official connectors:

- **Apple Notes** — [Claude Connectors Directory](https://claude.ai/connectors)
- **iMessage** — [Claude Connectors Directory](https://claude.ai/connectors)

Together, these packages give you full access to your Apple productivity stack.

## Privacy & Security

### What This Server Does
- **Local-only:** Runs entirely on your Mac; no data is sent to cloud servers
- **AppleScript bridge:** Drives native macOS apps via AppleScript; all operations stay within your operating system
- **No credentials stored:** The server delegates authentication entirely to macOS Keychain; no passwords or tokens are stored in the app

### Data Handling
- **Search results:** Returned to Claude within the current conversation; not logged or persisted
- **Message bodies:** Plain text only; HTML and embedded images are stripped to keep results within token limits
- **Permissions:** System Settings > Privacy & Security controls what the server can access
- **TCC sandbox:** Full Disk Access is required only for iCloud Drive; Mail/Calendar/Contacts/Reminders use narrower Automation permissions

### Transparency
For questions about how this server uses your data, see [PRIVACY.md](./PRIVACY.md) (link placeholder).

## Development

### Setup

```bash
cd apple-ecosystem-mcp
pip install uv                    # Install uv package manager
uv sync --dev                     # Install dependencies + dev extras
```

### Running Tests

```bash
# Core infrastructure tests (Phase 1)
uv run pytest tests/test_bridge.py tests/test_permissions.py tests/test_server.py tests/test_main.py -v

# All tests (mocked, no real Mac required)
uv run pytest tests/ -k "not live" -v

# Live macOS smoke tests (optional, requires real permissions)
APPLE_MCP_LIVE_TESTS=1 uv run pytest tests/live/ -v
```

### Running Locally in Claude Desktop

Before publishing to PyPI, test locally:

```json
{
  "mcpServers": {
    "apple-ecosystem": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/apple-ecosystem-mcp", "apple-ecosystem-mcp"]
    }
  }
}
```

Add this to `~/Library/Application Support/Claude/claude_desktop_config.json` and restart Claude Desktop.

### Project Structure

See [CLAUDE.md](./CLAUDE.md) for implementation contracts and [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) for phase-by-phase specifications.

## Troubleshooting

### "AppleScript failed" Error

If you see an AppleScript error, it usually means:
1. Missing macOS permission — restart and grant access in System Settings > Privacy & Security
2. Timeout (30s) — the app was slow to respond; try again
3. App not installed — ensure Mail, Calendar, Contacts, Reminders, or iCloud Drive is available

Check the system logs for details:
```bash
# View debug logs
tail -f ~/.claude/debug.log
```

### Full Disk Access Not Granted

iCloud Drive tools require Full Disk Access. To grant it:
1. System Settings > Privacy & Security > Full Disk Access
2. Click the + button
3. Navigate to `/Applications/Claude.app` (Claude Desktop) or your Terminal app (Claude Code)
4. Click Add

### Permission Denied (-1743)

This macOS error means the user denied permission for the app. To reset permissions and re-prompt:
```bash
# Reset Mail permission
tccutil reset Automation com.apple.Mail

# Then re-run the server and grant permission when prompted
```

## Contributing

This is a personal project. For bugs or suggestions, open an issue on GitHub.

## License

**MIT License**

Copyright (c) 2026 Abhinav Agrawal

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

**THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.**

---

### Summary of License Rights

Under the MIT License, you are free to:
- ✅ Use this software for any purpose (commercial, personal, private, or public)
- ✅ Copy, modify, and distribute this software
- ✅ Sublicense (include it in other projects)

The only requirements are:
- 📋 Include a copy of the license and copyright notice in any substantial portions of the software you distribute

No warranty is provided. The software is provided "as-is."

## Attribution

Built with:
- [FastMCP](https://gofastmcp.com) — MCP server framework
- [Model Context Protocol](https://modelcontextprotocol.io) — Standard protocol for AI-driven tool use
- macOS AppleScript — Native OS integration

## Author

**Abhinav Agrawal** — [GitHub](https://github.com/abhinavagrawal) | [Email](mailto:abhinavag@icloud.com)
