# Readiness and selection contract v1

`src/ecos/dispatcher/readiness.py` is a deterministic reference oracle for the future SQL
function; it performs no dispatch. Inputs are frozen at one database instant, sourced from
authoritative rows/versions. Its selection evidence wire schema lives under contracts/work.

Readiness (due/scheduled/retry time) is separate from eligibility (enabled/nonterminal),
dependency satisfaction, approval, maintenance, idempotency and safety. Capabilities and
heartbeat availability are evaluated per executor/work pair. Immediate `ready_override_at`
makes future due work ready after the override instant; it does not override retry backoff
or any safety gate. `priority_override` is a distinct bounded owner value with actor,
reason and expiry. An override without a live expiry has zero effect on ordering.

Among eligible pairs, order descending: active owner priority (-100..100), immediate-ready
flag, SLA breach seconds, deadline pressure seconds, business impact (0..100), recurrence
relative age basis points. Break ties by created_at then occurrence UUID ascending. Missing
SLA/deadline contributes zero; missing recurrence period uses one day. Deadline pressure
starts at 24 hours from deadline and grows after it. Relative age is elapsed overdue seconds
divided by recurrence period, floored in basis points. UTC instants are required.

This transparent lexicographic v1 is an initial engineering convention, not an optimized
weighted score. Future tuning requires a new policy version and regression fixtures, not
silent historical rescoring. The numeric windows/defaults need operational validation.

Persist the selected inputs, source record versions, gate reasons, evaluation instant,
policy version and tuple in the immutable execution start event. Rejected pair explanations
may be bounded diagnostics; do not continuously persist mutable Dispatch Rank on Tasks.
