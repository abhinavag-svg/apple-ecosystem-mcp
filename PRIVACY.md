# Privacy Policy — Apple Ecosystem MCP

## Overview

Apple Ecosystem MCP runs locally on macOS and gives Claude access to Apple apps and files that you explicitly choose to use. This document describes what the server can access, what it stores, and where data may leave your Mac.

## What The Server Accesses

Depending on which tools you invoke, the server may read or write:

- Mail
- Calendar
- Contacts
- Reminders
- Notes
- iCloud Drive

It can also read local metadata stores that macOS maintains for supported fallback and performance paths:

- Apple Mail Envelope Index for supported Mail metadata queries
- Apple Notes `NoteStore.sqlite` as a read-only fallback for large-note recovery

## What The Server Does Not Do

- It does not run a network service.
- It does not store passwords, tokens, or OAuth credentials.
- It does not sync your Apple data to a separate backend.
- It does not create its own mirrored Mail or Notes database.

## How Data Flows

```text
Claude Desktop / Claude Code
    |
    | MCP over stdio
    v
Apple Ecosystem MCP
    |
    +-- native helper (Calendar, Contacts, Reminders)
    +-- AppleScript (Mail, Notes, some fallback paths)
    +-- local filesystem / local metadata stores
```

This project itself is local-only. Data leaves your Mac only when you intentionally surface it through Claude in a conversation.

## Permissions

macOS permissions still control access:

| Surface | Typical permission |
|---|---|
| Mail automation | Automation -> Mail |
| Notes automation | Automation -> Notes |
| Calendar access | Calendars |
| Contacts access | Contacts |
| Reminders access | Reminders |
| iCloud Drive access | Full Disk Access may be required |
| Local Mail metadata provider | Full Disk Access may be required |

If a permission is missing, the affected tool should return a scoped error.

## Logging

- The server avoids surfacing raw AppleScript stderr to Claude because it may contain private data.
- Local debug logs may contain sanitized diagnostics for troubleshooting.
- The project is designed to avoid logging email bodies, note content, or contact data as part of ordinary operation.

## Storage

- Credentials are delegated to macOS and the user’s existing Apple app sessions.
- Preferences and scheduled-task definitions may be stored locally as configuration.
- The server does not persist general query results or create an app-data mirror.

## Result Limits

To keep responses practical and reduce accidental overexposure, several tool families truncate or bound returned data. Examples include:

- mail body previews
- note text
- large file reads
- broad search result counts

## Third-Party Services

This project does not directly transmit your Apple data to a third-party service on its own. If you use the tools through Claude, the information you choose to surface in the conversation is then governed by your Claude product and account settings.

## Contact

For privacy questions or concerns:

- GitHub: https://github.com/abhinavag-svg/apple-ecosystem-mcp
- Email: abhinavag@icloud.com
