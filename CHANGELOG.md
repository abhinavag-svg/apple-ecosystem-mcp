# Changelog

## v1.1.1 - 2026-06-30

### Calendar Reliability

- Made Calendar operations fall back to AppleScript on recoverable native Calendar permission and backend errors.
- Launched Calendar before AppleScript Calendar access so fallback paths can trigger macOS permission and app readiness behavior more reliably.
- Bounded broad Calendar event scans by limit and skipped slow calendars instead of letting one calendar stall the full lookup.
- Removed attendee expansion from the Calendar list fallback path to keep broad availability checks responsive.
- Added a guard so Calendar does not report an empty result when every fallback calendar timed out.

### Release Packaging

- Signed the bundled native helper with a stable ad-hoc bundle identifier during MCPB builds.
- Aligned the release script with `make build` so local and published MCPB artifacts use the same bundle assembly path.
- Added regression coverage for helper signing and Calendar fallback/timeout behavior.

## v1.1.0 - 2026-06-28

### MCPB Installability

- Changed the primary MCPB to use a Node runtime entrypoint for current Claude Desktop compatibility.
- Added a thin Node launcher that starts the existing Python tool engine from the bundled source tree and vendored Python dependencies.
- Kept the future `server.type = "uv"` manifest as a separate local build path instead of making it the default before Claude Desktop accepts it.
- Added MCPB validators for manifest shape, required files, forbidden local artifacts, runtime command safety, and GitHub author metadata.
- Updated the release/build flow to include `package.json`, `package-lock.json`, the Node launcher, vendored dependencies, and the native helper.

### Anthropic Submission Metadata

- Added `author.url` pointing to `https://github.com/abhinavag-svg` in every shipped manifest.
- Mirrored author metadata into `package.json` and `package-lock.json`.
- Added packaging tests so the GitHub author URL requirement does not regress.

### Native Permission UX

- Embedded macOS privacy usage descriptions into the bundled native helper for Calendar, Contacts, and Reminders.
- Added an original menu-bar companion app skeleton for checking service status, requesting permissions, opening settings panes, copying local commands, and configuring Claude Desktop for a dev checkout.
- Updated permission guidance so macOS-related guidance writes to stderr rather than corrupting MCP stdio.

### Contacts And Reminders Reliability

- Made Contacts operations fall back to AppleScript when native Contacts access is denied or unavailable.
- Fixed the Contacts AppleScript search fallback compile error caused by a stale handler outside the Contacts AppleScript dictionary context.
- Made Reminders read/write operations fall back to AppleScript on recoverable native helper errors such as access denial and EventKit backend failures.
- Added regression tests for Contacts and Reminders native-denial fallback paths.

### Documentation And Release Flow

- Updated README install language around the primary MCPB path, Node launcher compatibility, and future UV bundle.
- Preserved the README screenshot added directly on GitHub before this release.
- Updated the release guide and release script to validate the Node-runtime MCPB and build the helper with embedded permission metadata.
