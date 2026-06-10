# Standalone Mail Rework Plan

## Summary

Mail needs a separate design track because the current AppleScript approach is useful for narrow actions but unreliable for chronological inbox queries and broad triage. The key gap is not just timeout handling; `mail_search` is keyword/index driven and cannot reliably answer "show everything received after 10 PM last night."

## Product Thesis

Mail should become an inbox/query provider, not only an AppleScript search wrapper. Claude needs deterministic recency, stable message identities, mailbox scoping, and bounded body access before scheduled or triage workflows can feel reliable.

## Current Problems

- Date-based Apple Mail queries reflect Mail's index behavior, not a true chronological store query.
- There is no reliable `received_after` filter for "last N hours" workflows.
- Broad mailbox scans can time out or return stale-looking indexed matches.
- AppleScript message/body access is slow and sensitive to mailbox size.
- Scheduled jobs amplify these problems because they need predictable unattended reads.

## Near-Term Design Options

| Option | Summary | Pros | Risks |
|---|---|---|---|
| Mail SQLite provider | Read Mail's local Envelope Index and related message metadata directly. | Best fit for chronological inbox queries and stable IDs. | Mail database schema changes across macOS versions; Full Disk Access likely required. |
| Spotlight metadata provider | Query indexed mail metadata with `mdfind`/Metadata APIs. | Less invasive than DB access; can support recency filters. | Spotlight indexing can lag and may miss fields needed for message actions. |
| Hybrid provider | Use DB/Spotlight for search and AppleScript only for actions like move, flag, draft, send. | Keeps writes closer to Mail.app while improving reads. | More provider complexity and identity mapping work. |
| IMAP provider | Connect to accounts directly through IMAP. | Real mail protocol semantics. | Requires credentials/OAuth/account setup; weaker local-only story. |

## Recommendation

Start with a hybrid local provider:

- Read path: native/local metadata provider for chronological queries, mailbox scoping, unread/flagged filters, and message identifiers.
- Action path: keep AppleScript for send, draft, move, flag, and delete until identity mapping proves stable.
- Body path: lazy fetch by stable message identity with explicit limits.

## Workstreams

| Agent | Model | Ownership | Task |
|---|---:|---|---|
| M1 Mail Store Research | `gpt-5.4` medium | Local Mail data model | Inspect macOS Mail storage/index options and identify stable fields without copying external repo code. |
| M2 Query Provider Prototype | `gpt-5.4` medium | New mail provider | Prototype `received_after`, `before`, mailbox ID filters, unread/flagged filters, and deterministic sort. |
| M3 Identity Mapping | `gpt-5.4` medium | Mail action bridge | Map provider IDs to AppleScript-accessible messages for move/flag/delete/thread fetch. |
| M4 Safety/Permissions | `gpt-5.4-mini` medium | Permissions and errors | Add Full Disk Access diagnostics and structured errors without leaking message content. |
| M5 Tests/Docs | `gpt-5.4-mini` low | Unit tests and docs | Add fake local index fixtures, contract tests, and migration notes. |

## Legal And License Guardrails

- Use the referenced repositories only for architectural inspiration and feature-gap comparison.
- Do not copy source code, scripts, schemas, documentation text, or unique implementation structure.
- Re-derive behavior from Apple's local platform behavior and this project's existing contracts.

## Acceptance Criteria

- `mail_search` can answer true chronological queries such as received after a timestamp.
- Results are sorted deterministically by received date unless another sort is requested.
- `mail_search` exposes clear degraded states when the local index is unavailable.
- Existing write tools remain confirmation-gated and continue to use stable identities.
- Broad triage workflows no longer depend on AppleScript enumerating the whole mailbox.
