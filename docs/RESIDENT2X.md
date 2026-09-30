> **Owner correction 2026-09-29:** ECOS 2.x is production infrastructure.
> Authority transfers per functional domain; historical non-production descriptions below
> are superseded by [the production authority decision](PRODUCTION_AUTHORITY.md).
> A029/A047 remain 1X until Wave 1 acceptance and transfer; A029-B remains 1X.

# Resident Ada 2.x — pre-cutover executor

`runtime/resident2x/` is a separate executable plane. `src/ecos/` remains the pure,
offline contract/reference core. No active 1.x file or accepted SQL contract changes.
Start with [the disposition delta](RESIDENT2X_DISPOSITION_DELTA.md).

## Run

Install `requirements-resident.lock` in the separate development Python environment.
Use a restricted configuration produced by `scripts/resident2x_acceptance.py` or
an equivalent governed enrollment. No owner login is accepted by the child.

```powershell
.venv\Scripts\python.exe -B scripts\resident2x.py --config .local\resident2x-hosted-004\config.json
```

This is a foreground continuous loop; `--max-cycles 8` bounds an acceptance run.
No Scheduled Task, service, port listener or auto-start registration is installed.
The acceptance process exits after its bounded run. Its attestation expires after
two hours, heartbeat freshness after 90 seconds. Re-enrollment and production
launcher/credential lifecycle are operational acceptance work, not implied here.

State, requests, result artifacts, heartbeat, logs and the OS-released singleton
lock live under the configured `.local/resident2x-*` directory. The directory ACL
permits only its operator. Credentials stay in this ignored directory and never
enter a work package, CLI argument, log or committed evidence. The default harness
does not import enrollment, contact PostgreSQL, resolve Drive secrets or call providers.

SQL owns all dispatch state. The runtime registers, reports heartbeat, requests
work, fetches/revalidates the package, renews the fence, invokes an explicit
capability handler, verifies the result and completes through `ecos.operate`.
Unsupported handlers fail through `work.fail`; controlled disposition methods
support `work.defer` and `work.release`; graceful signal cancellation releases work.
Expired fences use the accepted bounded `recovery.sweep`, then request new work.
No private SQL helper or direct control-table write exists in the runtime.

Exact write requests are fsynced before sending. Ambiguous commits reuse the same
request/idempotency key after restart; the database still authorizes every replay.
The loop never treats a local result file as committed completion. Fact and terminal
occurrence readbacks use independent connections and recomputed canonical hashes.

## Evidence

- `docs/evidence/resident2x/hosted-004.json`: real persistent project
  `loonpojawpfagzobxoko`, process PID 25396, three succeeded occurrences, one fact.
- `local-007.json`: actual abrupt child exit after fact commit, lease expiry,
  renewed claim/version, one fact despite replay, all three capabilities complete.
- `phase2-regression.json`: 31 Phase 1 transactional checks, 38 Phase 2 checks,
  15-session same-work and different-work contention passed; disposable server stopped.
- `offline.json`: 61 active offline tests passed, 26 historical integration placeholders
  skipped; 10 new Resident safety tests. Historical skip labels are not live proof.
- `security.json`: exact known-secret comparison, token patterns, actual SQL denial
  probes, unchanged accepted contracts and 1.x source identity.
- Numbered failed reports preserve harness/bootstrap defects before successful runs.
  `local-003` was interrupted after a localhost connection stall before enrollment;
  explicit IPv4 plus a timeout fixed subsequent runs. No success is claimed for it.

Hello World occurrence `2b9345bf-1f0a-4bb5-8331-102e57ff649d` was claimed by instance
`d50696aa-a03b-43d7-b15b-1a692df58977` at claim version 1, run
`86317261-091d-4f93-bbdc-7bd75bcde1db`. The stored fact is
`5725578f-b931-4ce5-a8be-aeb25f7633f3`, exact statement `Hello World`, canonical hash
`26ce9945c2bd2906eea0a7dfbc22085d86b4ad0e270898c3abc5c8ee70313fe3`.
Its subject/source record explicitly identifies synthetic, acceptance-only Resident
Ada 2.x evidence. The child performed fact.record, scoped independent readback and
work.complete. Administrative setup only enrolled the synthetic fixture and login.

## TLS and dependency provenance

The public CA is from Supabase Studio's official
[certificate URL configuration](https://github.com/supabase/supabase/blob/master/apps/studio/hooks/custom-content/custom-content.json),
downloaded over HTTPS from
`https://supabase-downloads.s3-ap-southeast-1.amazonaws.com/prod/ssl/prod-ca-2021.crt`.
Its DER SHA-256 fingerprint is
`807025AD50D4ED219D2C9C7D299C004F824EB00CF7F65AFEF607D07B72E6CAFA`.
Both hostname and chain verification remain enabled (`verify-full`); no server
security setting was relaxed. See [Supabase SSL guidance](https://supabase.com/docs/guides/platform/ssl-enforcement).
The September 25 PostgreSQL 17.11 changelog was reviewed; no relevant ltree,
legacy pgcrypto or custom-operator change was introduced by this Python runtime.

Shared 1.x HTTP/request-binding/SMS dependency hashes are recorded in the acceptance
configuration and checked before import. `-B` and `sys.dont_write_bytecode` prevent
writing bytecode into the active 1.x release. Runtime1's PID 19856, release 1.0.011,
active pointer and dispatcher hash stayed unchanged while 2.x ran. The 2.x child has
its own login, instance, lock, state and heartbeat, and binds no production ports.
The loopback TLS test server belongs only to the acceptance harness and closes after it.
