# Apple Ecosystem MCP

Apple Ecosystem MCP is a local macOS MCP server for Claude Desktop and Claude Code. It exposes Mail, Calendar, Contacts, Reminders, Notes, and iCloud Drive through a mix of native macOS frameworks, AppleScript, and local filesystem access.

The project ships primarily as a Claude Desktop `.mcpb` bundle.

## What It Covers

- Mail
- Calendar
- Contacts
- Reminders
- Notes
- iCloud Drive
- Friendly-name preferences and stable target resolution
- Local scheduled tasks built on top of the same tools

## Example Prompts

These are the kinds of things the connector is built for:

- `Draft an email to Jane J saying we need to plan a meetup night next week in between the kids' schedule. Check her contact details, look at next week's calendar openings, and help me suggest a couple of realistic evenings.`
- `Find the latest thread with our school, check my calendar for this week, and draft a reply proposing two pickup-call times that do not conflict with anything.`
- `Look up David Chen in my contacts, find our recent email history, check when I'm free next Thursday, and draft a meeting follow-up with a few time options.`
- `Review tomorrow's calendar, my overdue reminders, and any unread important mail, then give me a short morning game plan.`
- `Find my Tuscany Itinerary note, pull the related calendar events and any travel emails, and help me assemble a clean trip summary.`

These are deliberately cross-app. The value is not just one tool at a time, but Claude being able to reason across Mail, Calendar, Contacts, Reminders, Notes, and files together.

## Scheduled Workflow Examples

Scheduled tasks are better for recurring read-heavy workflows than one-off commands.

- `Create a scheduled task that runs every weekday at 7:00 AM and prepares a daily triage summary from my calendar, reminders, and important unread mail.`
- `Create a scheduled task for Sunday evening that gives me a weekly planning digest with next week's events, overdue reminders, and open follow-ups.`
- `Create a scheduled task for 8:30 PM that generates a tomorrow preview with calendar events, due reminders, and anything I should prepare tonight.`
- `List my scheduled tasks and show me which ones are enabled.`

## Runtime Architecture

- Calendar, Contacts, and Reminders use a bundled native macOS helper.
- Mail uses AppleScript, with an optional local Mail metadata provider for supported date-window and mailbox metadata queries.
- Notes uses AppleScript for canonical reads, with a read-only Apple Notes store fallback for recovery from large-note failures.
- iCloud Drive uses local filesystem access.

More detail lives in [docs/architecture.md](./docs/architecture.md).

## Documentation

If you want the full story of the project, start here:

- [docs/README.md](./docs/README.md)
- [docs/product-story.md](./docs/product-story.md)
- [docs/development-history.md](./docs/development-history.md)
- [docs/architecture.md](./docs/architecture.md)
- [docs/roadmap.md](./docs/roadmap.md)

## Requirements

- macOS 13 or newer
- Claude Desktop or Claude Code
- For local development: `uv` and Xcode command line tools / `swiftc`

## Install In Claude Desktop

1. Download `apple-ecosystem-mcp.mcpb` from [GitHub Releases](https://github.com/abhinavag-svg/apple-ecosystem-mcp/releases).
2. Double-click the `.mcpb` file and install it in Claude Desktop.
3. Restart Claude Desktop if needed.
4. Grant macOS permissions when prompted.

## Local Development

```bash
git clone https://github.com/abhinavag-svg/apple-ecosystem-mcp.git
cd apple-ecosystem-mcp
make install
make test
make build
```

To run directly from a checkout in Claude Desktop:

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

## Permissions

The server stays local, but macOS still gates access through TCC permissions.

| Capability | Typical permission |
|---|---|
| Mail tools | Automation -> Mail |
| Notes tools | Automation -> Notes |
| Calendar tools | Calendars |
| Contacts tools | Contacts |
| Reminders tools | Reminders |
| iCloud Drive tools | Full Disk Access may be required |
| Local Mail metadata provider | Full Disk Access may be required |

If a permission is missing, the affected tool should fail with a scoped error rather than taking down the whole server.

## Tool Families

The server currently exposes 73 tools across:

- Mail
- Calendar
- Contacts
- Reminders
- Notes
- iCloud Drive
- Inventory / preferences / target resolution
- Scheduled tasks

To inspect the exact tool set after install, ask Claude to list available tools or call `apple_inventory`, `scheduled_tasks_list`, or one of the app-specific list tools.

## Scheduled Tasks

Scheduled tasks are local automations layered on top of the same MCP tools. They are intended for report-style and read-heavy workflows first, not background destructive actions.

Examples:

- daily triage
- tomorrow preview
- overdue reminders review
- weekly planning digest

## Privacy

- The server runs locally on your Mac.
- It does not host a network service.
- It does not store credentials.
- Data only leaves your Mac when you explicitly use it in Claude.

See [PRIVACY.md](./PRIVACY.md) for the full policy.

## Troubleshooting

Common fixes:

1. Re-grant macOS permissions in System Settings.
2. Restart Claude Desktop after granting new permissions.
3. Rebuild the bundle with `make build` if you are testing local changes.
4. Force legacy provider behavior for Calendar, Contacts, and Reminders with:

```bash
APPLE_ECOSYSTEM_MCP_PROVIDER=applescript
```

5. Mail defaults to AppleScript-first auto mode. To inspect Mail access options or open Full Disk Access settings:

```bash
uv run apple-ecosystem-mcp mail diagnostics --json
```

In Claude, use `mail_access_setup`.

6. Force Mail to stay on AppleScript:

```bash
APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER=applescript
```

7. Force Mail to use the local metadata provider when testing supported queries:

```bash
APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER=local
```

## Contributor Notes

For contributors and maintainers:

- Architecture: [docs/architecture.md](./docs/architecture.md)
- Prompt-routing reference: [docs/claude-prompt-dictionary.md](./docs/claude-prompt-dictionary.md)
- Broader project docs: [docs/README.md](./docs/README.md)

## License

MIT. See [LICENSE](./LICENSE).
