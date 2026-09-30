# Claim admission repair: candidate rejected for transfer

The fresh-read candidate addresses the reported selected-then-disabled sequence,
but does **not** satisfy the strict no-post-disable-new-claim invariant. It was
not installed. No domain transfer, Task Loop edits, Command Registry edits,
runtime restart, SQL mutation, Drive publication, or provider business action
was performed during this investigation.

## Verified source and paths

The installed 1.0.011 `resident_governed.py` preimage SHA-256 is
`61356177937cf02fe7841a90a059bfa1ea637ad2157eff03982889455c759b47`.
`ResidentGovernedDispatcher.claim` fresh-reads ownership and version but omits
Enabled and current admission checks. `SheetsTable.update_row` commits T:AA
through a separate unconditional `values.update` RPC. The local worker lock
does not serialize an external Sheets disable writer.

Resident's `_owned` and `_validate_delegated_claim` are existing-ownership guards,
not claim creators. Their accepting a legitimately acquired claim after disable
is required drain behavior and must remain intact.

Online/Scheduled uses the separate authoritative `Run Task Loop Item` procedure.
Its current final pre-write instruction requires a fresh worker/version read but
does not explicitly require renewed Enabled/maintenance admission. It also uses
separate connector read and ownership write operations. A Resident-only patch
does not repair that path. No separate executing Scheduled Ada instance was
instrumented, and no test result here is claimed as Online/Scheduled acceptance.

## Candidate and focused results

The candidate adds admission before reservation and again before the ownership
write, reusing `fresh_execution_decision`, `executor_local_admission`, and the
existing throttle check. Missing/ambiguous maintenance fails closed. Changed
worker definitions cause a rescan rather than stale execution. Existing owner
renewal/drain and provider fencing are unchanged. Disabled rejection does not
write attempt/retry fields.

16 synthetic focused cases passed, including eight concurrent contenders around
a disable during reservation. All nine requested categories are represented.
These tests exercise the actual candidate method against in-memory Sheets
doubles; they are **not the requested actual-running-runtime probe**.

One additional deterministic counterexample establishes the remaining failure:

1. All final reads see Enabled TRUE and eligible/unowned version N.
2. An independent disable writer commits Enabled FALSE.
3. The already prepared unconditional T:AA update commits version N+1.
4. Ownership readbacks match, and the candidate returns a valid claim.

The counterexample preserves Enabled FALSE throughout step 3. It requires no
cache, malformed data, provider effect, or claim-fence bypass. The test passing
means the unsafe interleaving was reproduced, not that the repair was accepted.

Adding another read only moves the gap. Rejecting every post-write disabled claim
would also reject a claim acquired before disablement, violating the explicit
existing-active-claim requirement. This cannot establish the required ordering.

## Remaining minimum requirement

The claim commit and disable operation need a shared, enforced ordering boundary
covering Resident and connector claim writers. No such conditional commit is
present in the inspected implementation. The existing immutable reservation
orders competing claimants; ordinary Enabled edits do not participate in it.
Changing that protocol or introducing a new persistence gateway exceeds this
bounded fresh-read repair and has not been implemented or presumed approved.

The prepared candidate must not be released as a transfer-safe fix. First resolve
the shared claim/disable commit boundary, then perform the requested running
Resident probe and Online/Scheduled acceptance. A domain-specific stop/drain is
an alternative transfer prerequisite, but is not evidence that the generic
no-new-claim invariant has been repaired.

## Wave 1 state and reused evidence

Fresh readback in this investigation: A029, A047, and A029-B are Enabled TRUE and
have empty Claim Token/Claimed By fields. No drain or pause was performed.
SQL independently returned `toast.acquisition=1X, epoch=1` and
`staffing.features=1X, epoch=1`. Neither domain was transferred.

Existing `WAVE1_ACCEPTANCE.md/json` evidence remains intact: two Toast closed-date
windows, four isolated SQL shadow batches, A029-B schema/calculation parity,
actual Resident 2.x crash recovery, Phase 1 31/31 and Phase 2 38/38 database
regressions, and prior security evidence. Those historical provider/database
checks were not repeated for this source-only candidate. They do not prove
production transfer, compatibility publication, or full domain rollback.

The original `scripts/wave1_legacy_pause_probe.py` is unchanged. Test JSON here
contains synthetic outcomes only. No credentials or production rows are included.

## Reproduce locally without installation

Supply the verified preimage to `build_candidate.py --source PATH`; it verifies
the pinned SHA before producing `resident_governed.py` beside these tools.
Run `test_claim_admission.py` with the existing HOME-01 Python/dependency runtime.
It imports supporting modules from the existing 1.0.011 slot and creates only
temporary synthetic claim locks and local test reports. Do not include generated
runtime source/preimage files in Git. Successful exit includes reproduction of
the known unsafe commit-boundary counterexample.
