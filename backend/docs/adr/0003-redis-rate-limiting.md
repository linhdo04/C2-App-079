Title: Use Redis for rate-limiting and ephemeral state
Date: 2026-06-07
Status: Accepted

Context

The app requires fast in-memory counters for rate-limiting and may need ephemeral caches.

Decision

Use Redis as the in-memory datastore for rate-limiting, shared locks, and short-lived state.

Consequences

- Pros: very fast, mature Redis ecosystem, atomic counters and TTLs.
- Cons: operational overhead (separate service) and need for connection/credentials management.

Alternatives considered

- In-memory local counters: simple but not safe for multi-process or multi-instance deployments.
- PostgreSQL advisory locks/counters: possible but heavier and slower.
