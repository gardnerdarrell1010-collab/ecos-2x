# Phase 1 concurrency acceptance correction — 2026-09-29

Authority: Darrell's Phase 1 completion instruction. Applies to C-01 only.
The original 100-session stress quantity was arbitrary, not derived from expected
ECOS concurrency. The owner directs 20 genuinely simultaneous independent PostgreSQL
sessions as a representative stress level materially above expected simultaneous
executor contention. This capacity assessment is an owner requirement, not a measured
production-load claim. Correctness and unrelated-work parallelism are the invariants.

Test A: 20 independent sessions, common start, one eligible occurrence, exactly one
winner and 19 valid losers, one live claim/run, matching fence/version/ownership.
Test B: at least 20 eligible independent occurrences, 20 independent sessions, 20
distinct claims satisfying capability/readiness. All claim operations must return
before any contender commits, proving absence of global queue serialization.

The current override is contracts/acceptance/phase1-concurrency.json. Historical
Phase 0 catalog, manifest, oracle fixtures and verification are unchanged. The
current evidence companion resolves this override explicitly. A connection failure,
broken barrier, sequential connector calls, or smaller sample cannot pass C-01.

Observed: 15 backend sessions reached the start barrier; five failed while connecting.
No claim operation ran. Test A is blocked and Test B was not run. This demonstrates
unavailable required capacity in this attempt, not a verified configured pool size.
No pool, compute, IPv4, credential, or network setting was changed. Owner resolution
of the 20-session prerequisite is required before retrying this gate.
