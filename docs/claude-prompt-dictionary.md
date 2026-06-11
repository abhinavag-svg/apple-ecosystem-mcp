# Claude Prompt Dictionary

This document exists to make tool use more deterministic.

It is the human-readable companion to the packaged prompt contract in
`src/apple_ecosystem_mcp/prompt_contract.py`. The runtime contract lives with
the code; this document is the contributor-facing version.

The core rule is simple:

- Claude should speak in natural language.
- Tools should operate on explicit fields and stable identities.
- Claude should not invent hidden search intent when the user asked for chronology, inventory, or direct lookup.

## Why Claude Assumed

When a prompt like `what emails did I receive overnight` reaches a tool surface that only offers a generic `mail_search`, the model may improvise. That usually looks like:

- converting a recency request into guessed keywords
- searching by topic instead of by time window
- returning inconsistent results across runs

That is not a memory feature. It is an intent-routing problem.

The fix is to make the routing contract explicit:

- chronology requests -> time-window query
- lookup requests -> exact identifier or exact resolved target
- keyword search requests -> keyword query
- cross-app workflow requests -> sequence the right tools, do not overload one tool

## Deterministic Routing Rules

Use these rules before calling any tool.

1. If the user asks for "recent", "latest", "overnight", "today", "yesterday", or "since <time>":
   - treat it as a chronology request
   - do not invent keywords
   - prefer `query=""`
   - pass explicit `since` / `before`
   - prefer account or mailbox filters when the user names them

2. If the user asks to "find", "search", "look up", or names a sender/topic:
   - treat it as a keyword or fielded search
   - use `query="<literal user intent>"`
   - add structured filters only when they were requested or clearly implied

3. If the user names a calendar, reminder list, mailbox, note folder, or contact group:
   - resolve the friendly name to a stable identity first
   - if resolution is ambiguous, stop and return the ambiguity explicitly
   - never silently choose one write target

4. If the user asks for "most recent across all accounts":
   - search across all supported accounts
   - annotate each result with `account_name`
   - do not collapse or relabel accounts mid-response

5. If the user asks for a summary:
   - use list/search tools first
   - fetch full bodies or threads only for the narrowed result set

## Prompt Dictionary

These examples are phrased as user prompts on purpose. Under each one is the intended tool behavior.

### Mail: chronology, not keywords

Prompt:
`What emails did I receive overnight in iCloud?`

Tool intent:
- `mail_recent(since=<last-night-cutoff>, before=<now>, filters={"account_name":"iCloud"})`

Do not:
- invent topic keywords
- search message bodies

Prompt:
`Show me the most recent emails across all my mailboxes and label which account each came from.`

Tool intent:
- `mail_recent(since=<recent-window>, limit=<n>)`
- response should preserve `account_name`

Prompt:
`What unread emails came in since 10 PM last night?`

Tool intent:
- `mail_recent(since="YYYY-MM-DDT22:00:00", filters={"unread":true})`

Prompt:
`Did I get anything from Fairmont today in iCloud?`

Tool intent:
- `mail_search(query="Fairmont", since=<today-start>, filters={"account_name":"iCloud"})`

### Mail: search, not chronology

Prompt:
`Find emails from Ankita about school pickup.`

Tool intent:
- `mail_search(query="school pickup", filters={"from_addr":"Ankita or resolved email if available"})`

Prompt:
`Search my mail for receipts from Apple with attachments.`

Tool intent:
- `mail_search(query="receipt", filters={"from_addr":"Apple", "has_attachments":true})`

### Calendar

Prompt:
`What is on my calendar tomorrow?`

Tool intent:
- `calendar_list_events(start_date=<tomorrow-start>, end_date=<tomorrow-end>)`

Prompt:
`Add dinner with Ankita next Thursday to Family calendar at 7 PM.`

Tool intent:
- resolve `Family` -> stable calendar ID
- `calendar_create_event(..., calendar_id=<resolved-id>)`

### Reminders

Prompt:
`What is overdue in my Personal reminders list?`

Tool intent:
- resolve `Personal` -> stable reminder list ID
- `reminders_list(list_id=<resolved-id>, overdue_only=true)`

Prompt:
`Add buy train snacks to Travel reminders.`

Tool intent:
- resolve `Travel` -> stable list ID
- `reminders_create(title="buy train snacks", list_id=<resolved-id>)`

### Notes

Prompt:
`Open my Tuscany Itinerary note.`

Tool intent:
- `notes_read(title="Tuscany Itinerary")`
- use exact note read path, not search preview as the final answer

Prompt:
`Find notes about Malta flights.`

Tool intent:
- `notes_search(query="Malta flights")`
- only call `notes_read` once a specific note is selected

### Contacts

Prompt:
`Look up Ankita and show me her preferred email and phone number.`

Tool intent:
- `contacts_search(query="Ankita")`
- then `contacts_get(contact_id=<resolved-id>)` if needed

### Cross-App Workflows

Prompt:
`Draft an email to Ankita saying we need to plan a date night next week between the kids' schedules. Check her contact card, look at next week's calendar openings, and suggest two realistic evenings.`

Tool sequence:
1. `contacts_search(query="Ankita")`
2. `calendar_list_events(start_date=<next-week-start>, end_date=<next-week-end>)`
3. synthesize candidate times
4. `mail_draft(...)`

Prompt:
`Review tomorrow's calendar, overdue reminders, and unread important mail, then give me a morning plan.`

Tool sequence:
1. `calendar_list_events(...)`
2. `reminders_list(...)`
3. `mail_recent(since=<recent-window>, filters={"unread":true})`

## Anti-Patterns

Claude should avoid these patterns:

- turning recency prompts into guessed keyword bundles
- silently picking one of several same-named targets for a write
- using full-content reads when list or preview data is enough
- converting "latest" into "top keyword match"
- hiding degraded states like permission failures or ambiguous resolution

## Suggested Tooling Improvements

This dictionary helps immediately, but the long-term fix is a slightly sharper tool surface.

Near-term improvements worth adding:

- `mail_recent_by_account` for multi-account summaries
- explicit mailbox/account inventory examples in tool descriptions
- stronger server-side validation for "chronology request with non-empty guessed query"

## Authoring Guidance

When adding new tools or examples, prefer:

- explicit time windows over words like "recent"
- stable IDs over display names on writes
- inventories and resolvers before mutations
- one tool per job shape instead of one overloaded "search" primitive
