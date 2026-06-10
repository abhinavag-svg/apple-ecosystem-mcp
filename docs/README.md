# Documentation Guide

This repo now has a small public docs spine plus a set of internal and historical documents.

## Start Here

If you want to understand the project quickly, read these in order:

1. [Product Story](./product-story.md)  
   Why this exists, which workflows it is designed to make boringly reliable, and the product principles behind it.

2. [Development History](./development-history.md)  
   The chronology of the project: what shipped when, which reliability problems surfaced, and how the architecture evolved.

3. [Architecture](./architecture.md)  
   The current technical shape of the system: native helper, AppleScript bridge, local metadata providers, packaging, and safety model.

4. [Roadmap](./roadmap.md)  
   What remains, especially the Mail redesign path and the next practical product improvements.

## Internal Working Docs

These are still useful, but they are closer to engineering process than public narrative:

- [session-state.md](./session-state.md) — running handoff state across sessions
- [TEST_PLAN.md](./TEST_PLAN.md) — test contracts and coverage notes
- [plans/](./plans/) — implementation plans, workstream planning, and milestone logs

## Historical Material

Older planning and release documents that shaped the repo are kept under [archive/](./archive/). They are useful for archaeology and blog-post source material, but they are no longer the best entry point.
