# Multi-Agent Execution Strategy

## Summary

This plan tracks the implementation strategy and blog-post-friendly rationale for using multi-agent execution while controlling cost, tokens, and tool usage.

V1 practical-use enhancements must precede V2 scheduled tasks because scheduled jobs need reliable defaults, aliases, and stable target resolution before they can run safely without repeated user clarification.

## Combined Agent Plan

| Phase | Agent | Model | Why This Model |
|---|---|---:|---|
| V1 | A1 Resolver/Preferences | `gpt-5.4` medium | Core resolution logic needs careful schema and edge-case handling. |
| V1 | A2 Container Inventory | `gpt-5.4-mini` medium | Mostly normalization of existing discovery outputs. |
| V1 | A3 MCP Preference Tools | `gpt-5.4-mini` medium | Thin wrappers over A1 behavior. |
| V1 | A4 Write Tool Integration | `gpt-5.4` medium | Write paths are safety-sensitive and cross-connector. |
| V1 | A5 Docs/Contracts | `gpt-5.4-mini` low | Documentation and examples are low-risk. |
| V2 | B1 Scheduler Config/Registry | `gpt-5.4` medium | Config validation and persistence need careful design. |
| V2 | B2 Workflow Runner | `gpt-5.4` medium | Orchestrates multiple connectors and failure modes. |
| V2 | B3 CLI + launchd | `gpt-5.4-mini` medium | Bounded CLI/plist generation work. |
| V2 | B4 MCP Scheduled Tools | `gpt-5.4-mini` medium | Thin MCP wrappers over scheduler APIs. |
| V2 | B5 Safety/Docs | `gpt-5.4-mini` low | Policy tests and docs are well-scoped. |

## Cost Controls

- Use `gpt-5.4-mini` for wrappers, documentation, simple CLI surfaces, schema-adjacent tests, and mechanical normalization.
- Use `gpt-5.4` for resolver logic, write-path integration, workflow orchestration, and scheduler config.
- Reserve `gpt-5.5` only for unexpected deep ambiguity in Apple identity behavior, scheduler design, or cross-connector safety.
- Keep the parent agent as integrator and reviewer rather than assigning overlapping write scopes to workers.

## Tool Budget Policy

- Prefer targeted `rg` and `sed` inspection over broad repo reads.
- Run targeted pytest commands first.
- Avoid the full suite unless targeted failures indicate shared behavior has broken.
- Avoid live macOS tests unless specifically validating real app behavior.
- Avoid network access.
- Avoid broad formatters or code generators that rewrite unrelated files.
- Keep worker ownership disjoint to reduce merge and review overhead.

## Blog Tracking Format

Track these fields at each milestone:

- agent/model used
- task ownership
- files touched
- tests run
- failures avoided
- why the model/tool choice was efficient

Use `docs/plans/implementation-log.md` as the append-only record.

## Operating Rules

- Start independent workstreams in parallel only when their write scopes are disjoint.
- Do not duplicate investigation between parent and worker agents.
- Parent agent reviews and integrates all worker changes.
- Workers must not revert unrelated edits.
- Escalate model strength only when the task complexity justifies it.
