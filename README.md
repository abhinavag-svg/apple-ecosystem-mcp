# Apple Ecosystem MCP

Apple Ecosystem MCP lets Claude work across the Apple apps you already use on your Mac: Mail, Calendar, Contacts, Reminders, Notes, and iCloud Drive.

It is built for everyday personal productivity: triage recent email, draft replies, plan around your calendar, find notes, check reminders, and assemble cross-app context without manually copying data between apps.

Everything runs locally through Claude Desktop or Claude Code. There is no hosted backend, no credential store, and macOS permissions remain in your control.

<img width="760" height="1180" alt="triage_screenshot" src="https://github.com/user-attachments/assets/adc64b6b-7a9a-4aae-8a71-985a3a175355" />

## What You Can Ask

Apple Ecosystem MCP is most useful when Claude needs to coordinate across apps.

Examples:

- `Triage my inbox from the last 10 hours and summarize anything urgent.`
- `Find emails from LinkedIn yesterday and open the most relevant one.`
- `Check tomorrow's calendar and overdue reminders, then give me a morning plan.`
- `Find my Tuscany Itinerary note and summarize the travel plan.`
- `Draft a reply to Jane using her contact info and my calendar availability.`
- `Find the latest school email, check this week's calendar openings, and draft a pickup-call reply.`

## Capabilities

### Mail

- Search recent, unread, sender, email-address, subject, and time-window queries.
- Read message metadata and body text for practical summaries.
- Open messages in Mail.
- Draft, send, move, flag, and delete messages with safer write paths.
- Use an AppleScript-first path with local Inbox metadata and message-file fallbacks for reliability.

### Calendar, Contacts, And Reminders

- Read and update calendar events.
- Search and inspect contacts.
- Create and manage reminders and reminder lists.
- Use a bundled native macOS helper for fast, stable local access.

### Notes

- List, search, and read Apple Notes.
- Prefer reliable plain-text reads for large rich notes.
- Fall back to the local Notes store when AppleScript body extraction is too expensive.

### iCloud Drive

- Browse and read local iCloud Drive files.
- Write or update files when explicitly requested.

### Scheduled Tasks

- Create local recurring report workflows such as:
  - daily triage
  - tomorrow preview
  - overdue reminders review
  - weekly planning digest

## Install In Claude Desktop

1. Download `apple-ecosystem-mcp.mcpb` from the latest GitHub release.
2. Double-click the `.mcpb` file.
3. Install it in Claude Desktop.
4. Restart Claude Desktop if needed.
5. Grant macOS permissions when prompted.

The `.mcpb` is the primary install path. Current Claude Desktop builds validate
local bundles as Node/Python/Binary extensions, so this local bundle uses a
Node.js launcher around the existing Python tool engine. A future `uv` runtime
bundle can be built separately once your Claude Desktop build supports MCPB
`server.type = "uv"`.

After install, ask Claude:

```text
Call apple_inventory.
```

## Requirements

- macOS 13 or newer
- Claude Desktop or Claude Code
- Apple apps configured locally on the Mac

For local development:

- `uv`
- Xcode command line tools / `swiftc`
- Node.js 18 or newer only if you are building the optional Node-compatible MCPB

## Permissions

macOS controls access through system permissions. Apple Ecosystem MCP uses those permissions rather than storing credentials.

| Capability | Typical macOS permission |
|---|---|
| Mail tools | Automation -> Mail |
| Notes tools | Automation -> Notes |
| Calendar tools | Calendars |
| Contacts tools | Contacts |
| Reminders tools | Reminders |
| iCloud Drive tools | Full Disk Access may be required |
| Local Mail metadata fallback | Full Disk Access may be required |

If a permission is missing, the affected tool should return a scoped error instead of taking down the server.

## Privacy

- Runs locally on your Mac.
- Communicates with Claude over local MCP stdio.
- Does not run a hosted service.
- Does not store Apple account credentials.
- Does not sync your Apple data to a separate backend.
- Data appears in Claude only when you ask Claude to use it.

See [PRIVACY.md](./PRIVACY.md) for the full policy.

## Troubleshooting

### A Tool Says Permission Is Missing

Open System Settings -> Privacy & Security and grant the relevant permission. Restart Claude Desktop after granting new permissions.

### Mail Search Or Reading Looks Stale

Mail uses an AppleScript-first path with local Inbox fallbacks for supported read workflows. In Claude, call:

```text
mail_access_setup
```

For local diagnostics:

```bash
uv run apple-ecosystem-mcp mail diagnostics --json
```

### Force A Provider During Testing

Use AppleScript for Calendar, Contacts, and Reminders:

```bash
APPLE_ECOSYSTEM_MCP_PROVIDER=applescript
```

Force Mail to AppleScript:

```bash
APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER=applescript
```

Force Mail to the local metadata provider:

```bash
APPLE_ECOSYSTEM_MCP_MAIL_PROVIDER=local
```

## Local Development

```bash
git clone https://github.com/abhinavag-svg/apple-ecosystem-mcp.git
cd apple-ecosystem-mcp
make install
make test
make build
```

`make build` creates the primary Node-launcher bundle at
`mcpb/apple-ecosystem-mcp.mcpb`.

To build the same Node.js launcher bundle under the explicit compatibility
target:

```bash
make build-node-mcpb
```

The Node bundle is intentionally separate from the primary install bundle. It is
a thin Node launcher around the existing Python tool engine, not a rewrite of the
Apple tools.

To build the future MCPB `uv` runtime bundle described in the public MCPB docs:

```bash
make build-uv-mcpb
```

Use that artifact only after confirming your Claude Desktop build accepts
`server.type = "uv"`.

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

Development docs live under [`docs/`](./docs/). They are useful for contributors, but they are not required to use the Claude Desktop bundle.

## Support

For support, bugs, and privacy questions:

- GitHub: https://github.com/abhinavag-svg/apple-ecosystem-mcp/issues
- Email: apple_anthropic_mcp@icloud.com

## License

MIT. See [LICENSE](./LICENSE).
