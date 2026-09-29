# Planned query contracts

Phase 1 implements readiness and flow health as SQL views/functions, with caller privilege
checks and explicit sensitivity projection. No persistent Dispatch Rank is introduced.

| View | Grain | Required columns/invariants |
|---|---|---|
| v_work_readiness | occurrence/executor instance | gate booleans, source versions, reason codes; incompatibility is pair-local |
| v_work_health | state/stage | exact ready, claimed, running, retry and dead-letter counts, oldest age and SLA |
| v_node_health | executor instance | server heartbeat age, expiry, availability, boot identity |
| v_outbox_health | destination | pending count, oldest committed age, claim expiry, dead letters |
| v_provider_reconciliation | command | unknown outcome age, evidence, strategy, required owner action |
| v_memory_heads | scope/kind | exactly one active version with authorization filtering |
| v_system_status_header | snapshot | source as-of instants and degraded chains; no false healthy |

Later dashboard/forecast views retain source snapshots, sample counts, source-set hash,
unknown/partial states, immutable forecast versions and closed-actual boundaries.
