# Roadmap

This roadmap is the current high-signal view of what matters next. It replaces the older habit of scattering future work across feature TODOs, planning prompts, and release notes.

## What Is Already In Place

The project already has:

- broad Apple app coverage
- stable target resolution and user preferences
- local scheduled tasks
- a native provider layer for Calendar, Contacts, and Reminders
- a pragmatic Notes connector
- a local Mail metadata provider for supported query shapes

That means the remaining work is less about basic coverage and more about reliability, ergonomics, and sharper workflows.

## Near-Term Priorities

### 1. Mail Rework

This is the biggest product and engineering priority.

Current Mail behavior can support useful actions and some metadata queries, but it still falls short on true inbox-first workflows such as:

- messages received after a timestamp
- dependable chronological triage
- mailbox-first recency scans
- predictable unattended scheduled reads

The direction is a hybrid Mail architecture:

- local metadata/index provider for reads
- AppleScript kept for actions until identity mapping is fully trustworthy
- bounded lazy body fetches

See [plans/mail-rework-plan.md](./plans/mail-rework-plan.md) for the detailed internal workstream.

### 2. Diagnostics Without Noise

The next polish layer should improve confidence without creating surveillance or clutter:

- better degraded-state reporting
- clearer permission and provider availability messages
- optional diagnostics that avoid leaking private content

### 3. Contract And Regression Coverage

The project would benefit from a little more defensive test coverage around:

- AppleScript shape regressions
- tool schema contracts
- JSON escaping edge cases
- packaging-time correctness

## Medium-Term Opportunities

### Workflow Packs

The repo already has the beginnings of a real workflow system. A natural next step is to make a few task families feel first-class:

- meeting prep
- account review
- weekly planning
- inbox follow-up
- file-and-note based project review

### Better Notes Semantics

Notes is currently pragmatic and useful. A later pass could make it richer without compromising reliability:

- more explicit rich-content handling
- export-friendly formatting choices
- clearer behavior for mixed-format notes

### Better User-Facing Configuration

There is a product opportunity around preferred mailbox, calendar, reminder list, and alias configuration. The foundations exist. A more intentional UX layer could make this much easier for non-technical users.

## Strategic Boundaries

Some things are deliberately not the current focus:

- a hosted backend
- multi-platform support
- cloud synchronization outside native Apple apps
- turning the MCP server into a long-running automation daemon

Those boundaries help keep the system local-first, inspectable, and opinionated.

## Internal Planning Sources

Detailed implementation planning still lives in:

- [plans/practical-use-enhancements.md](./plans/practical-use-enhancements.md)
- [plans/scheduled-task-capabilities.md](./plans/scheduled-task-capabilities.md)
- [plans/v3-native-and-near-term.md](./plans/v3-native-and-near-term.md)
- [plans/mail-rework-plan.md](./plans/mail-rework-plan.md)
- [plans/implementation-log.md](./plans/implementation-log.md)

Those are useful for engineering history and execution detail. This document is the concise product-facing roadmap.
