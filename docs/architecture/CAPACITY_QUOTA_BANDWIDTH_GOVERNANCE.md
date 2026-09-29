# Capacity, Quota and Bandwidth Governance

Requirement ID: **CAP-01**. Status: **DESIGNED — required forward capability**.
Owner authority: Phase 1 completion instruction, 2026-09-29. Planning phase: **Phase 2**.
This records a mandatory architectural requirement; no telemetry, quota scheduler,
provider integration or Phase 2 runtime is implemented by this Phase 1 change.

ECOS must govern and observe resource use with provider-specific limits, budgets,
measurement provenance, freshness and unavailable-measurement states. Missing
telemetry must not be presented as zero use. Thresholds are configuration grounded
in actual infrastructure/provider limits, with owner-governed changes.

| Area | Required measurements and governance |
|---|---|
| Executor capacity | Launcher cadence, execution duration, active executor count, overlap, saturation, DB operations per execution |
| Database capacity | Active client connections, pool utilization, query latency, lock waits, CPU, memory, disk I/O, rows scanned versus returned, growth and egress |
| Provider quotas | Applicable limits and budgets for Drive, Sheets while 1.x remains, Gmail, Toast, Twilio, Calendar, Vercel/Blob, financial providers, ChatGPT/Online Ada execution constraints and future providers |
| Bandwidth | Bytes received/transmitted, payload sizes, HOME-01 network consumption attributable to ECOS, unnecessary repeated reads and artifact transfer volume, measured where practical with coverage limitations recorded |
| Cost | Provider-specific free-tier limits, paid thresholds, operation/request budgets, storage, egress, compute and external API cost |

Routing must isolate resource pressure to dependent work where possible. Drive quota
pressure delays Drive-dependent work while pure DB work continues. Online Ada
saturation delays semantic work while DATABASE_DETERMINISTIC work continues. Toast
unavailability delays Toast-dependent work while unrelated work continues. DB connection
pressure triggers bounded backoff and connection reuse, preventing connection storms.

PostgreSQL performs filtering, joins, scoring, readiness and aggregation. Ada receives
the minimum governed work/context package necessary for the semantic operation, not
entire Tasks, Communications or history datasets. This reduces bandwidth, provider
requests, token/context use, latency and failure surface while preserving auditability.

After separately authorized cutover, ECOS 1.x Sheets becomes read-only historical/audit
state. Normal task/work dispatch must not depend on Sheets; PostgreSQL provides the
operational query/transaction system, with provider/artifact access only when required.
Sheets API request ceilings are a 1.x constraint, not a PostgreSQL requirement. Do not
invent SQL queries-per-minute limits modeled on Sheets. Govern actual connection use,
query performance, resources, locks, egress and infrastructure limits instead.

Phase 2 planning must define measurement sources, scoped budgets, routing policies,
owner escalation, and acceptance evidence. Required scenarios: targeted quota pressure
preserves unrelated throughput; connection pressure produces bounded reuse/backoff;
stale/missing metrics are visible; minimal governed context preserves operation/audit
semantics; cost and bandwidth coverage limitations are explicit. Implement only under
separate Phase 2 authorization. CAP-01 does not add a retrospective Phase 1 gate.
