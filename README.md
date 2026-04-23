# Apple Ecosystem MCP

An MCP server that bridges Claude to native macOS apps (Mail, Calendar, Contacts, Reminders, iCloud Drive) via AppleScript and Python.

**Requirements:** macOS 13+ with Claude Desktop or Claude Code

## Installation

### Claude Desktop (recommended for most users)

1. Download `apple-ecosystem-mcp.dxt` from [GitHub Releases](https://github.com/abhinavag-svg/apple-ecosystem-mcp/releases)
2. Double-click the `.dxt` file — Claude Desktop will prompt you to install it
3. Restart Claude Desktop and grant macOS permissions when prompted

### Claude Code

Install via `uvx` (requires uv package manager):

```bash
uvx apple-ecosystem-mcp
```

Or configure locally in `~/.claude/claude_desktop_config.json`:

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

## macOS Permissions

The server requires explicit user approval for each app category. When you first run the server, you'll see warnings for any missing permissions.

### Required Permissions

| Permission | System Settings Path | Used By |
|---|---|---|
| **Automation** → Mail | Settings > Privacy & Security > Automation | Mail tools |
| **Automation** → Calendar | Settings > Privacy & Security > Automation | Calendar tools |
| **Automation** → Contacts | Settings > Privacy & Security > Automation | Contacts tools |
| **Automation** → Reminders | Settings > Privacy & Security > Automation | Reminders tools |
| **Full Disk Access** | Settings > Privacy & Security > Full Disk Access | iCloud Drive tools |

### Granting Automation Permissions

1. Open System Settings > Privacy & Security > Automation
2. For each app (Mail, Calendar, Contacts, Reminders), ensure "Claude Desktop" or your Terminal app is listed with checkmarks next to the app
3. If missing, click the + button and add the app

### Granting Full Disk Access

For iCloud Drive support:

1. Open System Settings > Privacy & Security > Full Disk Access
2. Click the + button
3. Navigate to `/Applications/Claude.app` (Claude Desktop) or your Terminal (Claude Code)
4. Click Add

The server will continue to work even if permissions are missing; individual tools will fail with a clear error message.

## Tools

The server provides 34 tools across five apps:

### Mail (8 tools)
| Tool | Description |
|------|---|
| `mail_search` | Search inbox/sent by query, date range, sender |
| `mail_get_thread` | Fetch a full email thread by subject or ID |
| `mail_send` | Compose and send an email (dry-run by default) |
| `mail_create_draft` | Save a draft without sending |
| `mail_list_mailboxes` | List all mailboxes/folders across all accounts |
| `mail_move_message` | Move message to a mailbox |
| `mail_flag_message` | Flag or unflag a message |
| `mail_delete_message` | Delete a message |

### Calendar (7 tools)
| Tool | Description |
|------|---|
| `calendar_list_calendars` | List all calendars across all accounts |
| `calendar_list_events` | List events in a date range |
| `calendar_get_event` | Get details of a specific event |
| `calendar_create_event` | Create event with title, time, location, notes, invitees |
| `calendar_update_event` | Update an existing event |
| `calendar_delete_event` | Delete an event by ID |
| `calendar_find_free_time` | Find free slots between two datetimes |

### Contacts (5 tools)
| Tool | Description |
|------|---|
| `contacts_search` | Search contacts by name, email, phone, company |
| `contacts_get` | Get full contact record by ID |
| `contacts_create` | Create a new contact |
| `contacts_update` | Update fields on an existing contact |
| `contacts_list_groups` | List contact groups |

### Reminders (5 tools)
| Tool | Description |
|------|---|
| `reminders_lists` | List all Reminders lists |
| `reminders_list` | List reminders, optionally filtered by list or status |
| `reminders_create` | Create a reminder with due date, notes, priority |
| `reminders_complete` | Mark a reminder as complete |
| `reminders_delete` | Delete a reminder |

### iCloud Drive (5 tools)
| Tool | Description |
|------|---|
| `icloud_list` | List files and folders in iCloud Drive |
| `icloud_read` | Read a text or structured file |
| `icloud_write` | Write or update a file |
| `icloud_move` | Move or rename a file |
| `icloud_delete` | Delete a file (requires confirmation) |
| `icloud_search` | Search iCloud Drive by filename or content |

See [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) for detailed specifications and examples.

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

### Full Privacy Policy
See [PRIVACY.md](./PRIVACY.md) for the complete privacy policy and data handling practices.

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

### Local Development

If you're developing locally before publishing to PyPI, add this to `~/Library/Application Support/Claude/claude_desktop_config.json`:

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

Then restart Claude Desktop to pick up changes during development.

### Project Structure

See [CLAUDE.md](./CLAUDE.md) for implementation contracts and [IMPLEMENTATION_PLAN.md](./IMPLEMENTATION_PLAN.md) for phase-by-phase specifications.

## Troubleshooting

### "AppleScript failed" Error

If you see an AppleScript error:

1. **Check macOS permissions** — See [macOS Permissions](#macos-permissions) section above and verify all required permissions are granted in System Settings
2. **Restart Claude Desktop** — After granting new permissions, fully restart Claude Desktop (not just refresh)
3. **Timeout (30s)** — The app was slow to respond; try again, or check if the app is hanging
4. **App not installed** — Ensure Mail, Calendar, Contacts, Reminders, or iCloud Drive is available on your Mac

### Permission Denied Error (-1743)

This macOS error means the user previously denied permission. To reset and re-prompt:

```bash
# Reset Mail permission
tccutil reset Automation com.apple.Mail

# Reset Calendar permission
tccutil reset Automation com.apple.iCal

# Reset Contacts permission
tccutil reset Automation com.apple.Contacts

# Reset Reminders permission
tccutil reset Automation com.apple.reminders
```

After resetting, restart Claude Desktop and the app will re-prompt for permission.

### "Path escapes iCloud root" Error

This error occurs when using iCloud Drive tools with an invalid path. Ensure:
- Paths are relative to the iCloud Drive root (use `/` or `/folder/file.txt`, not absolute paths)
- Paths do not contain `..` segments or symlink escapes
- Files exist before trying to read them

### Debug Logging

For detailed error information:

```bash
# View server stderr (Claude Desktop logs)
log stream --predicate 'process == "Claude"' --level debug
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
