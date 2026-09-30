# Functional conversion checkpoint — 2026-09-30

Owner policy: two consecutive intended E2E passes with authoritative readback;
no stress, soak, restart or transient-failure matrix before functional cutover.

ONLINE_ADA_2X FUNCTIONAL / ACCEPTED. Owner accepted first scheduled window.
Second actual scheduled window: executor.register committed 18:12:43.705380 UTC,
heartbeat committed 18:12:58.621293 UTC, work.next NO_ELIGIBLE_WORK
18:13:07.207843 UTC. No manual Run now or substituted executor was used.
Accepted infrastructure was not retested. Existing 15 launchers remain enabled.

Ada Live Monitor FUNCTIONAL / ACCEPTED after two complete browser reloads.
The separate stabilization chat installed HTML 2.0.001 and an endpoint that
returned executor_read_failed. This chat repaired its database read via bounded
public.ecos_monitor_snapshot(), executable only by service_role. No table or
schema access was granted to anon/authenticated/service_role. Existing public
monitor endpoint behavior was retained; no credentials, claim fence tokens or
source payloads are returned. Migrations 29 and 30 are applied with exact hashes
in ecos_meta.schema_migration. Edge function version 2 invokes the bounded RPC.
Runtime presence selects active 2.x enrollments despite historical executor names.
Browser displayed current Resident and Online heartbeats, independently read
back from PostgreSQL. Older stale Resident enrollment remains visible honestly.

Canonical Drive HTML and both existing local launcher targets now use the same
2.x HTML. Prior local HTML was backed up; legacy sidecars and writers preserved.
Existing loopback monitor server was started at port 8765. Screenshot:
monitor-2x-accepted.png. No 1.x executor was restarted.

PostgreSQL conversion project: ECOS-2X-FUNCTIONAL-CONVERSION.
60 tasks: 55 existing function dispositions plus Online, Monitor, Interactive,
Resident and operational-state conversion control tasks. Online/Monitor/Resident are
completed; the remaining 57 are open. Existing 13-batch assignment and retirement
tail provenance preserved; classifications are not implementation acceptance.
Idempotent bootstrap and independent readback repeated once: 60 distinct tasks,
no duplicates, two completed. No new dispatcher tables or architecture.

Next: Interactive governed connection/enrollment is absent from enabled principal
bindings (the non-executor binding is a legacy publication guard, not Interactive).
Do not count administrator SQL as Interactive executor acceptance. Resident live
principal 3f0fa387-6379-4eca-85a9-072eb5e67379 remains healthy on its existing
runtime. Its second production Toast occurrence
63d36422-ebc2-4ab8-a056-91944b23ad73 passed, with independent restricted
ecos.toast_readback matching the runtime receipt content hash. First occurrence
daffc056-41c7-476b-927c-ef2bbd81dfd0 was already production-verified. Resident
governed read/write is FUNCTIONAL / ACCEPTED; whole capability conversions remain
pending. No provider business writes occurred. Five scoped migration tests passed.

Canonical source changes are local and unpublished. Existing approved public
HEAD f158126ad4de1690f00f639f1ab564fd65b3b7cc was not changed remotely.
