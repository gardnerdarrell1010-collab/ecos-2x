# Authority-effect fence candidate

Status: tested source; not installed or accepted for live authority transfer.

Migration 24 extends the existing domain owner, monotonic epoch and scoped
principal binding. It adds the canonical ecos.2x.execute requirement for
autonomous PostgreSQL consumers. Existing migrations 1 through 23 are unchanged.

External publication needs more than a check immediately before HTTP. The
existing provider command/attempt/result journal records an unresolved attempt
before the callback. The existing authority row remains locked through that
reservation transaction; its transfer trigger then rejects unresolved effects,
including after a client disconnect. Only independently verified output is
reconciled as successful. Ambiguous outcomes require governed reconciliation;
there is no timeout that silently restores transfer eligibility.

DomainEffects captures the grant once at execution start, confirms the reservation
transaction before invoking a provider, and records a stable readback evidence
hash. Stale grants, wrong domains, ungranted targets, and stale replays fail before
the callback. Completed replay performs readback without repeating mutation.

Validation: 76 offline checks passed, 26 integration placeholders skipped. The
disposable PostgreSQL harness passed 31 Phase 1, 25 Phase 2, 11 domain-authority,
11 batch, and 16 new effect checks, migration rebuild/repeat and concurrency.
These synthetic checks do not establish production installation or acceptance.

Remaining integration: wire both legacy A029 and A047 output boundaries to the
adapter; configure narrowly scoped credentials and grants; install an immutable
Resident successor through its verified lifecycle; enroll Resident 2.x; finish
the production compatibility publisher and A047 snapshot bridge; prove coherent
rollback and perform live acceptance before any domain transfer. Unknown Python
process identity prevented lifecycle verification; the Administrator preflight
was canceled. No retry or alternative elevation path was attempted.

Enabled is scheduling cleanup, not an authority fence. The prior claim-race
candidate is not a Wave 1 transfer prerequisite. Online scheduler activation is
deferred and is not a Resident Wave 1 blocker. A029-B remains unchanged.
