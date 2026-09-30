# Offline CI dependency correction

Workflow: Offline Phase 0 contracts. Run 36673774893 at c599834 failed in
`python scripts/check.py` on Ubuntu with exit code 1 and
`ModuleNotFoundError: No module named 'psycopg'`. Windows was canceled by matrix
fail-fast: its annotation explicitly names the failed Ubuntu job.

First known failing commit: 2426e73bd63970a5f7f92d36b3fccc23375034a8,
run 36651464940 on codex/resident-2x-runtime. Its actual Ubuntu logs show the
same missing psycopg import. Last known passing commit:
3c7e81fb07b793a085e4c7910ea16f94ba0f3157, run 36615002502.
Wave 1 descends from the Resident implementation and shares the root cause.

The local environment already includes psycopg; CI installed only the Phase 0
requirements. The correction installs the existing requirements-phase1.lock,
which includes requirements.lock plus the pinned PostgreSQL client and tzdata.
No new dependency versions, test changes, accepted-contract changes, skip flags,
continue-on-error, platform removal or notification changes are introduced.
Installing the client does not start a database or invoke live operations.

Future requirement only: GitHub Actions failures should feed ECOS Exceptions /
Notifications. Ingestion is not implemented here; failure email settings remain
unchanged. Final hosted CI must pass on both matrix platforms before preflight.
