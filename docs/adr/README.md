# Architecture decision records

All sixteen decisions record the supplied approved architecture direction. Status is accepted
for Phase 0 design, with operational implementation still DESIGNED. They do not approve
production provisioning, cutover, provider effects or the unresolved owner choices.

1. [PostgreSQL authority](ADR-001.md)
2. [Host boundary](ADR-002.md)
3. [One master](ADR-003.md)
4. [Task versus work](ADR-004.md)
5. [Selection and claims](ADR-005.md)
6. [Durable outbox](ADR-006.md)
7. [Provider effects](ADR-007.md)
8. [Semantic boundary](ADR-008.md)
9. [Capabilities](ADR-009.md)
10. [AI Memory](ADR-010.md)
11. [Recovery layers](ADR-011.md)
12. [Portability](ADR-012.md)
13. [External artifacts](ADR-013.md)
14. [Watchdogs](ADR-014.md)
15. [Quarantine](ADR-015.md)
16. [Maturity](ADR-016.md)

## Phase 1 implementation note

Phase 1 implementation notes: ../PHASE1_IMPLEMENTATION.md and ../PHASE1_SECURITY_PORTABILITY.md. ADR decisions and Phase 0 evidence remain historical. Typed model, role boundary, PostgreSQL operations, stage fencing, provider reconciliation, memory heads, bootstrap and migration ledger are BUILT; full concurrency/rebuild/restore acceptance remains pending.
