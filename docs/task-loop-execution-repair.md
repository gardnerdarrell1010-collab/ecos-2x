# Task Loop execution repair while production is off

The existing selector operates on granted `work_occurrence` rows, not on the
presence of migrated `task` rows or worker definitions alone. The operational
hookup left A027/A028 without an occurrence and seeded the other five periodic
definitions with zero business importance and installation-time due dates.
The preserved Task Loop source already contained the missing values.

`scripts/repair_task_loop_population.py` reconciles the seven existing periodic
definitions using the preserved PostgreSQL migration source. It retains original
fields, instructions, commands and derived values in the existing work context;
maps dispatch importance and schedule/retry boundaries to existing selector
inputs; and preserves an outstanding RUN NOW request's original timestamp.
It never enables an executor or definition and rejects previously executed or
ambiguous occurrence histories. It introduces no SQL scoring formula, scheduler,
worker timer, executor, domain or business entity.

The existing SQL lexicographic ranking, dependencies, retry gates, claim fencing,
completion and wakeup mechanisms are unchanged. Historical spreadsheet scores
are provenance, not replacements for current SQL selection evidence. The scope
is the seven already mapped periodic definitions, not an assertion that all
55 historical functions have executable implementations. A031's existing
communication handoff remains unchanged; no held backlog is replayed.

Exactly two consecutive internal passes completed, each selecting and completing
seven items through the real SQL boundary on disposable PostgreSQL. The tests use
preserved ranking inputs and copies of the approved Online/Resident identities,
verify the expected lexicographic order independently, exercise RUN NOW and a
dependency, reject wrong/stale fences, read packages and completion back, then
verify the next selection. No provider handler or business mutation is invoked.

Receipt SHA-256:
`a0d2df9a2c7f43c0b9c1dfcaffca6a6e4c5a29777e1009ad45dc78e6a7832aae`

Production remains disabled. The prepared Resident release still requires the
existing Administrator installation before A027/A028 can execute. Hosted
ChatGPT tool refresh/execution has not been verified after browser access was
denied. These deployment gates are separate from the internal selector passes.
