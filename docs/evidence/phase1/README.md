# Observed Phase 1 evidence

database-observations.json contains actual connector results, not simulated acceptance.
bootstrap-observed.json is the actual synthetic database package independently validated
against the Python contract verifier (73 schemas). Its transaction was rolled back.
The durability fixture is deliberately retained and both outbox items are delivered.
The SQL files ending _observed contain that run's exact synthetic IDs; read them as a
reproduction trace and substitute fresh seed readbacks on a newly authorized test target.
PHASE1_VERIFICATION.json records final successful counts separately from corrected failed
attempts. The deliberate migration-drift error is expected negative-test evidence.
Phase 0 reports and baseline inputs were not modified.
