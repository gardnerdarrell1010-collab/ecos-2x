# Initial managed PostgreSQL host adapter

Supabase is planned as the initial host. There is no project ID, credential, CLI dependency,
configuration requiring a live project, or provider-specific SQL in this repository.
No project/database was created. No SQL ran against Supabase.

Keep hosted auth, backup/PITR, secrets, Realtime, pg_cron and webhooks outside canonical
correctness. Replacements: ordinary API identity provider, PostgreSQL/logical backup operator,
external secret manager, durable outbox polling and portable scheduler. Host-specific scripts
may be added here only in a later authorized phase. Private core schemas are not exposed tables.
If later exposure is chosen, design explicit grants/RLS and API authorization together.

Region/tier/cost/RPO/retention need owner choices. Review host documentation again when actually
provisioning; Phase 0 has no dependency on the current hosted feature set or extension catalog.
