# Product Story

## The Job

Apple Ecosystem MCP exists to make Claude useful inside the real Tuesday-afternoon mess of a Mac-native working life.

That means fewer demo-y tool calls and more end-to-end jobs like:

- find the right email thread, check calendar constraints, draft the reply, and set a reminder
- prepare for a meeting by pulling together contacts, events, notes, and files
- run a daily or weekly planning ritual against real inboxes, calendars, and task lists
- let users speak in friendly names while the system quietly resolves to stable identities

The ambition is not “connect Claude to Apple apps.” The ambition is “make Apple-native knowledge work feel operationally fluid.”

## Product Principles

### 1. Friendly On The Surface, Stable Underneath

People think in names: “Work,” “Personal,” “Finance,” “The David calendar.”

Systems need stable identities: mailbox IDs, calendar UIDs, reminder list IDs, contact identifiers.

That is why this project adopted the rule:

> Claude should speak in friendly names, but tools should operate on stable identities.

This avoids the classic “which Work?” failure mode and lets workflows stay human without becoming ambiguous.

### 2. Boringly Reliable Is The Magic

The goal is not cleverness for its own sake. The goal is to make the obvious workflows so dependable that they stop feeling risky.

That drove several choices:

- explicit defaults and aliases
- structured ambiguity errors instead of guesses
- confirmation gates for destructive actions
- bounded result sets and truncation
- local-first execution
- scheduled workflows that start as read-heavy reporting, not background destruction

### 3. Productivity Is Cross-App

The real value is not in one connector at a time. It is in orchestration:

- Mail plus Calendar plus Reminders
- Contacts plus Calendar plus Files
- Notes plus Reminders plus scheduled digests

This project treats Apple apps as one operational surface rather than six isolated APIs.

### 4. Practical Use Beats Abstract Completeness

The connector set is shaped around workflows people actually try:

- triage today
- tomorrow preview
- overdue reminders review
- meeting prep
- account review
- inbox follow-up

That bias is why the repo eventually added preferences, target resolution, scheduled tasks, and native reliability work. Without them, the raw connectors existed, but the practical experience still had friction.

## Why The Architecture Evolved

The product philosophy showed up directly in the engineering:

- AppleScript was enough to prove usefulness, but not enough to make high-volume reads reliable.
- Stable IDs mattered more as soon as multiple mailboxes, calendars, and reminder lists entered the picture.
- Scheduled tasks required defaults, aliases, and safety constraints before they could be trusted.
- Native frameworks became necessary once Calendar, Contacts, and Reminders needed to feel fast and predictable.
- Mail earned a separate redesign track because keyword search is not the same thing as a true chronological inbox query.

## What This Repo Signals

If someone reads this project carefully, I want them to see three things:

1. A productivity obsession: the workflows are grounded in real working habits, not generic connector demos.
2. Product judgment: the system keeps choosing reliability, clarity, and humane defaults over flashy surface area.
3. Engineering depth: when the first architecture stops being good enough, the project changes the architecture instead of rationalizing the bug.
