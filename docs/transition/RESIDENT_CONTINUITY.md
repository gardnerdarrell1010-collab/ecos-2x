# Resident 2.x continuity

Migration 27 keeps the existing governed heartbeat and exact capability enrollment.
Only an administrator can enable renewal for an existing capability row and its
attester, approved runtime evidence hash, lease length and owner authorization.
The executor cannot create policies, grant new capabilities, change versions or
enable itself. Disabling a policy prevents further renewal; disabling the executor
also blocks heartbeat and work. Existing attestations retain their bounded expiry.
First enrollment renews once, then renewal occurs during the configured expiry window.
An enabled enrollment can recover an expired attestation on registration/heartbeat.

Rollback-only hosted acceptance verifies a one-second synthetic attestation,
renewal, expiry recovery, hash mismatch, revocation, helper permissions, and full
rollback. Run `python scripts/resident2x_renewal_acceptance.py` explicitly; the
offline harness never opens a database. Production readback on 2026-09-30 verified
five capabilities renewed automatically by the existing Resident heartbeat.

The Resident preserves its active claim and journal when database retries are
exhausted, reconnects with capped backoff, and registers again. Governance rejection
still fails closed. A keepalive connection failure retains its original error type;
an ambiguous database response is never converted into a terminal capability failure.

`scripts/resident2x_watchdog.py` validates the installed release and uses the same
OS singleton lock. A healthy locked Resident is left running. A stale locked
Resident is reported as unhealthy and is never duplicated or killed. Otherwise
the watchdog starts the same enrolled runtime with the same config and journal.

`scripts/install_resident2x_startup.ps1` requires an already-elevated Administrator
PowerShell. It verifies exact clean Git HEAD, installed file hashes and the running
release. It installs one limited-user S4U Scheduled Task with startup and one-minute
restart opportunities; PostgreSQL still owns business work selection. It does not
stop a runtime, change 1.x, create credentials, perform authority transfers or apply
migrations. Its immediate check verifies the existing healthy Resident is preserved.
Actual reboot acceptance remains a separate gate; task definition readback is not
proof of a completed machine restart. No UAC handoff is invoked.

Migration 28 admits only registration and heartbeat for an enabled renewal
enrollment after its generation attestation expires. The domain/epoch check stays
active; the approved runtime hash is checked during renewal. All business work
continues to require an unexpired ecos.2x.execute attestation. Authenticated
rollback acceptance through ecos.operate proves expired work rejection, renewal,
subsequent eligibility, wrong-hash ineligibility and revoked-enrollment rejection.
Run `python scripts/resident2x_reentry_acceptance.py` explicitly.
