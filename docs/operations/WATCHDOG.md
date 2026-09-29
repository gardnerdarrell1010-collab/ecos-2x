# Independent flow monitoring

Two independent layers are required: a DB-host watchdog outside normal Ada/notification
processing, and an external uptime monitor outside the primary database host. The emergency
path cannot depend on the dispatcher/outbox it is diagnosing. Provider/channel/recipients
remain OWNER-04; this repository sends no test alerts.

Check server-received heartbeat expiry, ready-work age, outbox lag, receipt backlog,
dead-letter growth, unresolved provider outcomes, failed backups/restore age and absence
of watchdog heartbeats. Health is unknown/degraded when evidence is missing; never infer
healthy from a worker's completion string. Deduplicate alerts and record recovery evidence.

Future failure injection: withhold a heartbeat; prove threshold detection and a real independent
alert with provider proof. Then stop primary API/database and prove the external monitor still
alerts. Verify the emergency path itself and recipient acknowledgement. These live tests
need explicit later authorization and cannot pass as Phase 0 fixture tests.
