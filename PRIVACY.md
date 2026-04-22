# Privacy Policy — Apple Ecosystem MCP

## Overview

The Apple Ecosystem MCP server bridges Claude to native macOS applications. This document explains what data it accesses, how it handles that data, and what privacy controls you have.

## Data Access & Storage

### What Data the Server Accesses

The server **reads** data from:
- **Mail.app** — email messages, mailboxes, sender/recipient info
- **Calendar.app** — events, attendee lists, timing and location info
- **Contacts.app** — contact names, email addresses, phone numbers, company info
- **Reminders.app** — reminder titles, due dates, priority, and notes
- **iCloud Drive** — files and directories (with Full Disk Access permission)

The server **writes** data to:
- **Mail.app** — draft messages, sent messages (only on explicit user request)
- **Calendar.app** — events, event metadata (only on explicit user request)
- **Contacts.app** — new contacts, contact edits (only on explicit user request)
- **Reminders.app** — new reminders, completion status (only on explicit user request)
- **iCloud Drive** — files and directories (only on explicit user request)

### What the Server Does NOT Do

- ❌ Does not upload your data to any cloud service
- ❌ Does not store email bodies, calendar event details, or contact info outside your Mac
- ❌ Does not cache search results or message history between sessions
- ❌ Does not share your data with third-party services
- ❌ Does not store passwords or credentials

## How Data Flows

```
Your Mac (Mail.app, Calendar.app, etc.)
    ↓ AppleScript (local process-to-process)
    ↓
Apple Ecosystem MCP (stdio, local)
    ↓ MCP Protocol (over stdio)
    ↓
Claude Desktop / Claude Code (local)
    ↓ Claude API (encrypted HTTPS)
    ↓
Anthropic Claude servers
```

**Within this conversation:**
- Data you share with Claude (search results, email previews, event details) stays within the current conversation
- Claude may train on conversations (subject to your Claude account settings)
- You can delete conversations at any time to remove the data

**Outside this conversation:**
- The server does not log or persist any data to disk
- Debug logs go to `~/.claude/debug.log` and contain only error traces (stderr from AppleScript), not user data
- Logs are cleared on restart

## macOS Permissions (TCC)

macOS requires explicit user approval for apps to access sensitive data. The server respects these permissions:

| Permission | Controls | Granted By |
|---|---|---|
| Automation → Mail | Access to Mail.app via AppleScript | System Settings > Privacy & Security > Automation |
| Automation → Calendar | Access to Calendar.app via AppleScript | System Settings > Privacy & Security > Automation |
| Automation → Contacts | Access to Contacts.app via AppleScript | System Settings > Privacy & Security > Automation |
| Automation → Reminders | Access to Reminders.app via AppleScript | System Settings > Privacy & Security > Automation |
| Full Disk Access | Access to iCloud Drive files | System Settings > Privacy & Security > Full Disk Access |

**You are in control:** You can revoke any permission at any time by removing the app from System Settings. Once revoked, the server cannot access that data.

## Result Size & Truncation

To keep results within Claude's token limits, the server truncates large data:

- **Email bodies:** Plain text only, max 8,000 characters. HTML and embedded images are stripped.
- **Search results:** Limited to 20–100 results per query (depending on subsystem)
- **Contact notes:** Max 2,000 characters
- **File reads:** Max 10 MB per file

These limits are enforced **before** the data reaches Claude, preventing very large attachments or document bodies from bloating conversations.

## Error Handling & Logging

When an error occurs, the server:
- ✅ Logs AppleScript stderr to `~/.claude/debug.log` at DEBUG level (for troubleshooting)
- ✅ Shows you a clean error message in Claude
- ❌ Never includes raw stderr (which may contain email subjects, contact names, or file paths) in the error shown to Claude

Example:
```
stderr (logged to debug.log only):
  error: "Abhinav Agrawal" is not allowed to send Apple events to com.apple.Mail

message shown to Claude:
  AppleScript failed (exit 1)
```

This prevents your personal data from being inadvertently surfaced in Claude conversations.

## Your Rights & Controls

### Access Your Data
The server only accesses data you ask it to. Every query is explicit:
- "Find emails from..." (search, no auto-sync)
- "Create a reminder..." (explicit create)
- "Move this message to..." (explicit move)

There is **no background sync, no automatic data collection, and no continuous monitoring.**

### Control Data Access
- **Revoke permissions:** System Settings > Privacy & Security > remove the app
- **Delete data locally:** Delete emails, events, reminders, or files from their native apps — the server won't see them
- **Delete conversations:** Delete conversations in Claude to remove the session data

### Request Deletion
If you believe your data has been stored or transmitted outside your control, contact:
- **Author:** Abhinav Agrawal (abhinavag@icloud.com)
- **GitHub Issues:** [apple-ecosystem-mcp/issues](https://github.com/abhinavagrawal/apple-ecosystem-mcp/issues)

## Third-Party Services

This server does not integrate with third-party services. It uses only:
- **FastMCP** — local framework for MCP server implementation
- **Model Context Protocol** — Anthropic standard for AI tool use
- **macOS AppleScript** — native OS integration

## Security Considerations

### What This Server Does Well
- ✅ All data stays on your Mac until you share it with Claude
- ✅ Credentials are never stored — all auth is via macOS Keychain
- ✅ AppleScript sandboxing prevents arbitrary file access outside iCloud Drive
- ✅ User data is passed safely to AppleScript (no injection vulnerabilities)

### What to Be Aware Of
- ⚠️ Claude conversations may be used for model improvement (subject to your account settings)
- ⚠️ Network requests to Anthropic are unencrypted by this server — use HTTPS (Claude.ai/Desktop does)
- ⚠️ Other users on your Mac can access the server's debug logs if they have admin access

## Policy Changes

This privacy policy reflects the current implementation (Phase 1). As new features are added in future phases, this policy will be updated.

**Last updated:** April 2026

## Questions?

For privacy questions, open an issue on GitHub or email the author:
- **Email:** abhinavag@icloud.com
- **GitHub:** https://github.com/abhinavagrawal/apple-ecosystem-mcp
