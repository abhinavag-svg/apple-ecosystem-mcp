# Development History

This document is the clean chronology of how Apple Ecosystem MCP evolved from an AppleScript-heavy connector into a more deliberate local productivity system.

## Phase 1: The Bridge

The project started with a straightforward premise: make Claude useful against the Apple apps many Mac-native users already live in every day.

The first generation focused on:

- a local FastMCP server
- AppleScript bridges into Mail, Calendar, Contacts, and Reminders
- iCloud Drive filesystem access
- packaging and installability

This phase established the core local-first posture, the basic tool surface, and the security contracts around AppleScript argument passing, result shaping, and confirmation-gated writes.

## Phase 2: Feature Depth

Once the base bridge was working, the next step was connector depth rather than architectural change.

Examples from this stage:

- better Mail search filters and stable message IDs
- richer Calendar event handling
- more structured Contacts results
- stronger Reminders metadata
- safer iCloud Drive reads and writes

This phase proved the project could be broad, but it also surfaced the limits of “just add more tools.” The system had coverage, but not always dependable workflow ergonomics.

## Phase 3: Practical Use

This was the first big product-thinking turn.

The question changed from:

> “What tools are missing?”

to:

> “What jobs should Claude be able to complete end-to-end without becoming confusing?”

That led to:

- preferences
- aliases
- stable target resolution
- `apple_inventory`
- consistent container metadata
- safer write targeting

This is where the repo became much more opinionated in a good way. The system stopped treating ambiguous user language as a caller problem and started treating it as a product problem.

## Phase 4: Scheduled Work

Once targets could be resolved reliably, scheduled tasks became viable.

The project added:

- local scheduled task config
- `launchd` integration
- MCP wrappers for task creation and control
- report-style workflows such as daily triage and tomorrow preview

This mattered because it turned the system from “interactive tools only” into “local recurring productivity workflows.” It also forced safety decisions: scheduled tasks started read-heavy on purpose.

## Phase 5: Reliability Pressure

Real-world usage exposed a recurring truth: `osascript` is useful, but finicky.

The practical problems were not abstract:

- timeouts on broad reads
- large-note failures
- AppleScript sensitivity to app state and mailbox volume
- inconsistent reliability across app domains

At this point, the repo stopped pretending every subsystem wanted the same backend.

## Phase 6: Native Provider Layer

Calendar, Contacts, and Reminders moved toward a bundled native helper, while Python stayed the public MCP surface.

That architecture kept the server easy to package and reason about while moving the most reliability-sensitive domains onto first-class macOS frameworks.

This phase introduced:

- a Swift helper binary
- a Python provider layer
- structured native error envelopes
- a cleaner separation between public MCP contracts and backend implementation

The important design win here was continuity: tool names and schemas stayed stable while the backend got more trustworthy.

## Phase 7: Notes And Mail Hardening

The next reliability work focused on the places where users were actually hitting pain:

### Notes

Large rich notes exposed the cost of reading giant HTML blobs through AppleScript. The fix was not a grand rewrite. It was a maintenance-minded change:

- plain-text AppleScript reads became the canonical path
- NoteStore remained a read-only fallback
- the system preferred consistency and consumability over preserving raw rich HTML

### Mail

Mail exposed a deeper problem.

The issue was not only timeout handling. The issue was that AppleScript keyword search is not a true chronological inbox query model.

That led to:

- a local Mail metadata provider for supported read patterns
- a clearer distinction between metadata queries and action paths
- a separate Mail rework track for true recency and mailbox-first workflows

## What Changed In The Shape Of The Project

Looking across versions, the project matured in three distinct ways:

### Product Maturity

It moved from connector coverage to workflow reliability.

### Architectural Maturity

It moved from one backend style to a mixed architecture chosen per domain.

### Operational Maturity

It added preferences, scheduling, packaging discipline, targeted testing, release hygiene, and better documentation.

## Current Character

Today the repo is best understood as:

- a local MCP server
- a productivity layer across Apple apps
- a reliability-focused mixed-backend system
- a project that takes the “last 20 percent” of product polish seriously

That last part is what gives it personality. The system keeps getting pushed past “technically works” toward “actually feels dependable.”
