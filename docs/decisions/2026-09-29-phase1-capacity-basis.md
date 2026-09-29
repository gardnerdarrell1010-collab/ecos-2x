# Current Phase 1 concurrency capacity basis

Owner-directed correction, 2026-09-29. Supersedes the 100-session quantity and the
20-session decision, retained as historical evidence. Both were arbitrary stress
quantities rather than requirements derived from the current execution topology.

Current designed maximum: **10 executors** = up to 8 overlapping Online Ada
executions under unusually long execution duration, 1 Interactive Ada, 1 Resident Ada.
Acceptance stress envelope: **15 independent simultaneous PostgreSQL sessions**,
150% of the designed maximum, a **50% margin**. This is the owner-provided design
basis, not a measured production saturation claim. A live executor does not
continuously hold a database connection; connection pooling and reuse are expected.
Launcher cadence is executor/platform configuration, never a permanent DB invariant.

C-01 requires same-work mutual exclusion and different-work parallelism. Test A:
one eligible occurrence, 15 sessions, exactly 1 owner and 14 valid losers, one live
claim/run with matching fences and versions. Test B: at least 15 eligible occurrences,
15 sessions, 15 distinct valid claims. Every claim call returns before any contender
commits, excluding accidental global queue serialization in this tested path.

Both tests passed against development through the existing SSL Session Pooler.
Independent backend PIDs, common start barrier, precommit barrier, timed observations,
claim/run identities, fences, readiness and final completion readback are retained in
docs/evidence/phase1/concurrency-15.json and concurrency-15-readback.json.
No pool or compute setting changed. Phase 0 evidence is unchanged. Reassess this
envelope explicitly if designed topology changes; do not infer unlimited capacity.
