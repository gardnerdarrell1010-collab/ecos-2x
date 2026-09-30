# Wave 1: tested shadow execution, production transfer blocked

Verified 2026-09-30 UTC. ECOS 2.x is production infrastructure; authority remains
assigned per domain. The production database is at canonical migration 23.
`toast.acquisition` (A029/A047) and `staffing.features` (A029-B) remain owned by
1X at epoch 1. No 1.x Task Loop fields, installed runtime files, Drive artifacts,
or Staging Records were changed by this work.

## Delivered and verified

| Check | Evidence |
|---|---|
| Production authority correction | Forward migrations 21–23 applied and independently read back; immutable migrations 1–20 preserved |
| Scope and authority | Unknown enrollment fails closed; object grants, domain, execution mode and epoch checked; cached Toast replay rechecks scope |
| Domain transfer control | Active domain claims block transfer; ownership changes require a new epoch and evidence; immutable audit history |
| Existing provider/business logic | Installed A029 acquisition, staffing normalization, and A047 projection imported after SHA-256 verification |
| Real Toast windows | Closed dates 2026-09-27 and 2026-09-28; current/future schedule family retained separately; A047 prior/current-day partial semantics retained |
| Parity | Captured identical inputs compared with installed reference functions: normalized values, aggregate totals, labor evidence, material hashes, bounded A047 projection |
| A029-B compatibility | Exact existing input schema/hash checked; unchanged installed `summarize` produces identical features and subsequent verified no-op for both windows |
| Actual Resident execution | Dedicated least-privilege Resident process selected, claimed, renewed, acquired Toast, committed batches, independently read them back, and completed two shadow occurrences |
| Recovery | Real process exit after acquisition and after SQL commit; lease expiry, restart, and governed recovery completed each occurrence with exactly one batch |
| Batch integrity | Atomic batch/checkpoint commit; checkpoint compare-and-swap; unique occurrence; immutable batch; conflicting replay rejected; open business dates rejected |
| Regression | 63 offline tests passed, 26 historical integration placeholders skipped; separate PostgreSQL Phase 1 31/31, Phase 2 38/38, authority 11/11, batch 11/11 |
| Contention | 15 sessions: same occurrence 1 winner/14 valid losers; distinct occurrences 15 winners |
| Existing Resident capabilities | Separate disposable process regression passed Hello World, artifact read, authenticated HTTP read, secret redaction, and singleton exclusion |
| Security | TLS verify-full, dedicated logins, no executor table DML or private-helper execution, no PUBLIC private helpers; new tables use deny-by-default RLS |
| Teardown | All three shadow enrollments retired: login disabled, binding/executor disabled, definitions disabled; zero active 2.x claims and zero available 2.x executors |

The Toast provider saw authentication plus reads only. The four committed shadow
batches are in the production database, isolated from production execution mode.
There was no authoritative Wave 1 production run or compatibility publication.
The canonical A029-B Drive input and its 1.x consumer were not changed.

## Genuine transfer blocker: existing 1.x pause fence

The installed 1.0.011 `resident_governed.py` SHA-256 is
`61356177937cf02fe7841a90a059bfa1ea637ad2157eff03982889455c759b47`.

`scripts/wave1_legacy_pause_probe.py` calls its actual methods with synthetic
in-memory records and a temporary local claim lock. It performs no production
reads/writes or provider calls. The sequence is:

1. The selector admits an enabled item.
2. The authoritative record is changed to `Enabled=FALSE` before claim.
3. `ResidentGovernedDispatcher.claim` fresh-reads that disabled record but still
   writes a claim. Its final pre-write read checks claim version/identity, not
   Enabled or domain ownership (installed lines 1371–1472).
4. `_owned` and `_validate_delegated_claim` both accept that claim despite the
   disabled record (lines 1474–1481 and 1152–1167).

This reproduces a safety counterexample; it does not claim a production duplicate
actually occurred. A disable/readback alone cannot prove the required invariant
that a previously selected 1.x occurrence cannot become authoritative after
transfer. Claim expiry checks do not fix this gap: the new claim is valid.

The existing local claim lock covers only its claim transaction. The probe uses
that lock normally and still reproduces the issue. A safe transfer needs an
acknowledged domain quiescence barrier covering every authorized execution path,
or a governed correction to the existing final claim/provider authority checks.
Neither has been established in the installed release. Stopping shared ECOS 1.x
is outside this assignment's explicit transfer boundary.

Therefore A029 and A047 were not disabled and ownership was not transferred.
A029-B remains enabled and its latest independent live read showed Completed.

## Remaining gates and continuation

SQL authority rollback/epoch fencing is proven in disposable tests. Full domain
rollback, compatibility publication recovery, and live 1.x eligibility restoration
are not yet proven. The production handler deliberately rejects activation until
these Wave 1 gates pass; this is a Wave 1 acceptance gate, not a global prohibition
on production ECOS 2.x execution.

After the 1.x quiescence issue is resolved, complete the minimal canonical
AFR-ECOS-000252 publication and registry/hash readback, unchanged A029-B handoff,
A047 immutable Staging snapshot compatibility, separate existing worker schedules,
and full domain rollback proof. Then perform the already-authorized conditional
domain transfer. No Wave 2 or Wave 4 work is included.

Private source captures, exact IDs, metadata preimages and detailed reports remain
in ignored, protected `.local` storage on HOME-01. Only sanitized verification
summaries belong in this public repository. Evidence inventory is in
`WAVE1_ACCEPTANCE.json`; the installed-runtime pause probe is reproducible separately
from the offline harness.
