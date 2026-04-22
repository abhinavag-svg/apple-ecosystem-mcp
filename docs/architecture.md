# Architecture — Apple Ecosystem MCP

## System Overview

```
┌─────────────────────────────────────────────────┐
│           Claude / AI Clients                    │
└────────────────┬────────────────────────────────┘
                 │ MCP Protocol
┌────────────────▼────────────────────────────────┐
│     Apple Ecosystem MCP Server                  │
│  ┌──────────────────────────────────────────┐  │
│  │  Tool Router                              │  │
│  │  - Dispatches requests to service libs   │  │
│  │  - Aggregates responses                  │  │
│  └──────────────────────────────────────────┘  │
│                    │                            │
│  ┌─────┬──────────┼──────────┬────────┐        │
│  │     │          │          │        │        │
│  ▼     ▼          ▼          ▼        ▼        │
│ ┌──┐ ┌──┐ ┌──────┐ ┌──┐ ┌───────┐             │
│ │IA│ │iC│ │iTunes│ │AS│ │Health│             │
│ │M│ │lo│ │ Music│ │ │ │      │             │
│ │  │ │ud│ │      │ │  │ │      │             │
│ └──┘ └──┘ └──────┘ └──┘ └───────┘             │
│ Service Libraries                               │
│ (read-only queries, parsing, transformation)   │
└────────────────┬────────────────────────────────┘
                 │ HTTP / REST
┌────────────────▼────────────────────────────────┐
│        Apple Public APIs                        │
│  (App Store, iCloud, iTunes, Health, etc.)    │
└─────────────────────────────────────────────────┘
```

## Module Organization

### `/src/servers/`
Each Apple service has its own isolated implementation:
- **`iam-server.ts`** — Identity & Account Management
  - User profile queries, account status, device list
  - No write operations (read-only)
  
- **`icloud-server.ts`** — iCloud Services
  - File storage status, backup info, settings
  - Calendar/contact metadata queries

- **`itunes-music-server.ts`** — iTunes Music
  - Library browsing, playlist info, purchase history
  - Playback metadata, recommendations

- **`appstore-server.ts`** — App Store
  - App info lookup, ratings, pricing
  - Purchase/subscription status

- **`health-server.ts`** — Apple Health
  - Health data summaries (via HealthKit)
  - Metrics and trends

### `/src/lib/`
Shared utilities:
- **`auth.ts`** — OAuth token management, refresh
- **`http.ts`** — Rate-limited HTTP client with retries
- **`parser.ts`** — XML/JSON response parsing
- **`types.ts`** — Shared TypeScript interfaces
- **`cache.ts`** — In-memory cache with TTL

## Data Flow

### Query Example: "List my purchased apps"
```
Client Request
    ↓
Tool Router (appstore-server)
    ↓
HTTP Client (with auth header)
    ↓
App Store API → XML Response
    ↓
Parser (extract app list)
    ↓
Type Check (ensure AppInfo shape)
    ↓
Response to Client
```

## Key Constraints

1. **Read-only:** All services are query-only (no mutations). Design decisions are in commits; see git log.
2. **Rate Limiting:** Apple APIs enforce per-IP limits. Cache aggressively; client retries with exponential backoff.
3. **Auth:** OAuth tokens expire. Refresh tokens stored in memory (not persistent) per request.
4. **Schema Stability:** Breaking changes in Apple API responses may require version bump. Update TypeScript types in `src/types/`.

## Testing Strategy

- **Unit tests:** Mock API responses, test parsers and type guards in isolation
- **Integration tests:** Hit staging/sandbox APIs if available; real requests to public read endpoints if not
- **E2E:** Manual verification with real Apple accounts (quarterly)

See [../tests/](../tests/) for test structure.

## Dependencies

| Package | Purpose | Risk |
|---------|---------|------|
| `mcp` | Protocol implementation | Low (Anthropic-maintained) |
| `node-fetch` | HTTP client | Low (widely used) |
| `xml2js` | XML parsing | Low (stable, security reviewed) |

No authentication libraries in deps — tokens are client-provided (zero storage risk).

## Deployment

Runs as standalone MCP server:
```bash
node dist/index.js
```

Claude connects via stdio. No database, no persistent state.

## Future: Data Sync

If we add write operations later:
- Implement transactional guards
- Add audit logging
- Require explicit user confirmation for mutations
- Review Apple ToS compliance

For now: read-only by design.
