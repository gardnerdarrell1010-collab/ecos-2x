"""Reproducible architecture registries and Phase 1 acceptance manifest."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = {}


def put(path, data):
    DATA[path] = data


def build():
    put("config/lifecycle-transitions.json", {"schema_version":"1.0.0", "policy":"Allowed edges still require governed gates and evidence", "transitions":{
        "task_lifecycle":{"draft":["open","cancelled"],"open":["waiting","completed","cancelled"],"waiting":["open","completed","cancelled"],"completed":["open"],"cancelled":["open"]},
        "approval":{"pending":["approved","rejected","changes_requested","expired"],"approved":["revoked","expired"],"rejected":[],"changes_requested":[],"expired":[],"revoked":[]},
        "work_occurrence":{"pending":["ready","cancelled"],"ready":["claimed","cancelled"],"claimed":["running","retry_wait","cancelled"],"running":["succeeded","retry_wait","failed","cancelled"],"succeeded":[],"retry_wait":["ready","dead_lettered","cancelled"],"failed":["dead_lettered"],"dead_lettered":[],"cancelled":[]},
        "delivery":{"planned":["ready","held","cancelled"],"ready":["held","sending","cancelled"],"held":["ready","cancelled"],"sending":["delivered","failed"],"delivered":["acknowledged"],"failed":["ready","cancelled"],"acknowledged":[],"cancelled":[]},
        "provider_outcome":{"pending":["accepted","succeeded","failed","unknown_outcome"],"accepted":["succeeded","failed","unknown_outcome"],"succeeded":[],"failed":["pending","reconciled"],"unknown_outcome":["reconciled"],"reconciled":["pending"]},
        "maturity":{"designed":["built"],"built":["end_to_end_verified"],"end_to_end_verified":["shadow_verified"],"shadow_verified":["production_verified"],"production_verified":[]},
        "claim":{"active":["released","expired","revoked"],"released":[],"expired":[],"revoked":[]},
    }})
    put("docs/architecture/baseline-provenance.json", {
        "review_date":"2026-09-28", "current_authority":"ECOS 1.x",
        "production_spreadsheet_id":"1LF0isNKZBgEbr8E_pzekSWJ8-iXGfGn3e3xteKuivu0",
        "review_time_continuity":{"business_id":"MEM-ECOS-000036", "rolling_version":94},
        "fresh_production_read_performed":False,
        "scope":"Approved review snapshots, not a fresh claim about live production",
        "sources":[{"path":p.relative_to(ROOT).as_posix(), "sha256":hashlib.sha256(p.read_bytes()).hexdigest()}
                   for p in sorted((ROOT / "docs/baseline").glob("*.md"))],
    })
    capabilities = [
        ("db.governed_operations","DATABASE_DETERMINISTIC","Validate/commit business state, audit and outbox"),
        ("db.claims","DATABASE_DETERMINISTIC","Atomic claims, fences, renewals and recovery"),
        ("db.features","DATABASE_DETERMINISTIC","Deterministic projections and feature computation"),
        ("semantic.interpret","ONLINE_SEMANTIC","Interpret source evidence into versioned proposals"),
        ("semantic.draft","ONLINE_SEMANTIC","Draft governed content with source references"),
        ("semantic.forecast","ONLINE_SEMANTIC","Explain and propose forecasts using frozen inputs"),
        ("semantic.memory_compact","ONLINE_SEMANTIC","Propose continuity versions with manifest"),
        ("human.review","INTERACTIVE_ADA","Present human decisions through governed operations"),
        ("provider.gmail","RESIDENT_DETERMINISTIC_PROVIDER","Gmail receipt/draft/approved transport and reconciliation"),
        ("provider.drive","RESIDENT_DETERMINISTIC_PROVIDER","Drive materialization and hash verification"),
        ("provider.toast","RESIDENT_DETERMINISTIC_PROVIDER","Acquire closed actuals with checkpoint evidence"),
        ("provider.twilio","RESIDENT_DETERMINISTIC_PROVIDER","SMS transport and reconciliation"),
        ("provider.calendar","RESIDENT_DETERMINISTIC_PROVIDER","Calendar references and delta ingestion"),
        ("provider.finance","RESIDENT_DETERMINISTIC_PROVIDER","Read account facts with as-of provenance"),
        ("provider.publication","RESIDENT_DETERMINISTIC_PROVIDER","Publish approved artifact versions"),
        ("provider.owner_review","RESIDENT_DETERMINISTIC_PROVIDER","Receive review packages and ACK after commit proof"),
        ("local.render","RESIDENT_DETERMINISTIC_PROVIDER","Safe templates, sample isolation, exact byte readback"),
        ("recovery.export","RESIDENT_DETERMINISTIC_PROVIDER","Create independent logical/portable packages"),
    ]
    put("config/capabilities.json", {"schema_version":"1.0.0", "routing_source":"stage_capability_requirement",
        "hybrid_is_surface":False, "capabilities":[{"name":n,"version":1,"surface":s,"description":d} for n,s,d in capabilities],
        "availability_policy":{"source":"server-received heartbeat + boot identity + capability attestations",
            "stale_heartbeat":"ineligible pair; preserve verified work", "heartbeat_interval_seconds":30,
            "heartbeat_ttl_seconds":90, "status":"development defaults; production tuning pending"}})
    provider_rows = [
        ("google_drive","Google Drive","file bytes, provider revisions and permissions","artifact/version IDs, URI, hash, size, provenance, provider-command evidence","file ID/revision/hash readback","object storage or filesystem adapter"),
        ("gmail","Gmail","messages, drafts, threads, labels and send evidence","durable receipt and exact content/hash, thread/message/draft IDs, delivery policy and result","message/draft identity + bounded history query; ambiguity held","mail adapter with explicit approval policy"),
        ("toast","Toast","POS source transactions and closed actuals","normalized facts, batch/source checkpoint, closed-date boundaries and hashes","source ID/date-range totals and closed status","POS acquisition interface"),
        ("twilio","Twilio","transport message SID and delivery status evidence","receipt, command, attempt, SID, status event and reconciliation result","SID/status query; unknown send without SID held for review","SMS transport interface"),
        ("google_calendar","Google Calendar","calendar event revisions and recurrence data","external event references, version, timezone, reminder obligation and policy key","event ID/version and delta cursor","calendar interface"),
        ("vercel_blob","Vercel/Blob","deployed release/alias and externally hosted bytes","publication target, immutable release/version IDs, artifact hash and readback","deployment ID, alias and exact artifact readback","HTTP host plus object-storage adapter"),
        ("financial_connectors","financial connectors","account/provider balances and transactions","as-of bounded account snapshot, source IDs, evidence, explicit unknowns","provider record IDs/as-of reconciliation","finance adapter"),
        ("supabase","Supabase","managed-host backup/service metadata only; PostgreSQL data remains ECOS authority after cutover","host-neutral operational rows, migration ledger, backup metadata, external secret references","PostgreSQL transactions and portable logical restore","standard PostgreSQL plus operations API/worker"),
        ("chatgpt","ChatGPT","no ECOS business-state authority; optional conversation evidence only","validated proposal/evidence and governed memory references","schema/hash/source-version verification","any competent semantic executor"),
        ("resident_runtime","Resident Ada local runtime","local process/file observations only","executor boot/heartbeat/capabilities, run/stage evidence and file hash","boot identity, fence validation and exact byte readback","capable replacement local runtime"),
    ]
    put("contracts/providers/boundaries.json", {"schema_version":"1.0.0", "providers":[{
        "provider_id":pid, "name":name, "authoritative_externally":pid not in {"supabase","chatgpt","resident_runtime"},
        "authority_scope":authority, "ecos_stores":stores, "idempotency_and_reconciliation":reconcile,
        "portable_replacement":replacement, "secret_storage":"external secret references only",
        "phase0_effects_allowed":False, "retry_policy":"unknown outcome requires reconciliation; never assume native idempotency",
        "policy_gate":"Gmail sends held for explicit approval until standing authority decided" if pid == "gmail" else "governed operation and provider-specific authorization"
    } for pid,name,authority,stores,reconcile,replacement in provider_rows]})
    mappings = [
        ("Contacts","MIGRATE","party person party_identifier","Validate identity; reconcile collisions before promotion"),
        ("Organizations","MIGRATE","party organization party_identifier","Validate organization identity and provider references"),
        ("Relationships","MIGRATE","party_relationship","Validate both endpoints and effective interval; quarantine malformed edges"),
        ("Projects","MIGRATE_CURRENT_STATE","project","Preserve current governed project state; archive history"),
        ("Tasks","MIGRATE_CURRENT_STATE","task task_assignment task_schedule task_dependency approval_request task_evidence","Separate obligation from runtime; nullable project; discard persisted rank/leases; type-check drift"),
        ("Communications","MIGRATE_CURRENT_STATE","provider_receipt communication communication_processing","Preserve exact provider evidence; split attempts; archive excess payload by approved retention"),
        ("Notification Queue","MIGRATE_CURRENT_STATE","notification","Duplicate IDs require source locators and identity resolution"),
        ("Notification Deliveries","MIGRATE_CURRENT_STATE","delivery delivery_attempt provider_command","No inferred sent status; reconcile provider evidence before any retry"),
        ("Artifacts","MIGRATE","artifact artifact_version","Retain stable external URI/provider IDs/hash and provenance"),
        ("Authoritative Files","MIGRATE","artifact artifact_version publication_target","Preserve external file authority and canonical-version evidence"),
        ("Facts","MIGRATE","fact","Typed subject/provenance/effective time; unsupported assertions quarantined"),
        ("Settings","REBUILD","typed_configuration","Preserve approved semantics; reject free-text type ambiguity"),
        ("Validation Lists","REBUILD","controlled_vocabulary","Map only approved values; unknown lifecycle strings require explicit disposition"),
        ("Workflow Dependencies","REBUILD","work_dependency task_dependency","Classify business versus runtime edge; reject cycles"),
        ("Task Loop","REBUILD","work_definition work_stage_definition task_schedule capability","Preserve 55 business capabilities using disposition registry; no row-per-service port"),
        ("Run Control","ARCHIVE_REFERENCE","legacy_run_evidence execution_event","115 duplicate Run IDs at review; only curated verified evidence can promote, never launcher noise"),
        ("Staging Records","ARCHIVE_REFERENCE","quarantine_item semantic_proposal provider_receipt","Migrate unresolved items only after hash/schema/identity proof"),
        ("Integrity Checks","REBUILD","integrity_finding assertion_catalog","Constraints, flow health and semantic audit replace sheet completion claims"),
        ("Ingestion State","MIGRATE_CURRENT_STATE","provider_checkpoint","Only checkpoints verified against provider boundaries promote"),
        ("Forecast Data Audit","REBUILD","forecast_source_snapshot","Preserve useful source evidence; rebuild typed accountability"),
        ("Forecast Performance","REBUILD","forecast_snapshot forecast_actual_reconciliation","Review had zero populated rows; never infer historical accountability"),
        ("AI Memory","MIGRATE","memory_record memory_version memory_scope memory_reference memory_compaction_run","Immutable history, active heads, explicit supersession; review-time MEM-ECOS-000036 v94 only"),
        ("Recovery Map","ARCHIVE_REFERENCE","backup_record export_package restore_test","Retain recovery evidence; replace mechanisms with portable recovery"),
        ("Ingestion Log","ARCHIVE_REFERENCE","legacy_ingestion_evidence","Curate checkpoint proof; retain raw evidence outside hot state by approved policy"),
        ("Activity Log","ARCHIVE_REFERENCE","legacy_activity_evidence","Preserve selected audit evidence; do not reinterpret narrative as success"),
        ("Exceptions","MIGRATE_CURRENT_STATE","exception_case integrity_finding","Keep unresolved exception/owner action with evidence and sensitivity"),
        ("System Bootstrap","REBUILD","bootstrap_package","Rebuild deterministic retrieval from current structured authority"),
        ("Sheet Registry","REBUILD","schema_registry migration_mapping","Translate record-family authority; archive sheet layout references"),
        ("Command Registry","REBUILD","operation_registry","Explicit allowlisted operations with auth/version/idempotency semantics"),
        ("Data Dictionary","REBUILD","schema_registry","Canonical SQL/JSON Schema vocabulary replaces column positions"),
    ]
    put("contracts/migration/legacy-mapping.json", {"schema_version":"1.0.0", "review_date":"2026-09-28",
        "classifications":["MIGRATE","MIGRATE_CURRENT_STATE","ARCHIVE_REFERENCE","REBUILD","RETIRE"],
        "source_authority_revalidation":"Before any extraction, read live System Bootstrap first and current registry; Phase 0 did not reread production",
        "families":[{"source_family":family,"classification":classification,"target_objects":targets.split(),
            "rule":rule,"identity_key":"source_system + family + batch_id + source_locator; legacy ID is nonunique evidence",
            "promotion_gate":"typed validation + explicit identity resolution + transformation version + reconciliation report",
            "raw_preservation":"immutable access-controlled batch outside Git"} for family,classification,targets,rule in mappings]})
    decisions = [
        ("OWNER-01","Production region and managed backup/PITR tier","No provisioning; cost review required", "production hosting"),
        ("OWNER-02","RPO/RTO and retention periods","Proposed operational RPO <=15m, export <=24h, RTO <=4h; daily35/monthly13/annual7 not authorized", "production recovery"),
        ("OWNER-03","Gmail standing send authority","Draft and explicit approval only; no standing send authority inferred", "autonomous Gmail send"),
        ("OWNER-04","Emergency watchdog channel/provider and recipients","No real alert channel configured", "live watchdog proof"),
        ("OWNER-05","Legal retention by data class","No purge; use synthetic data only", "production retention"),
        ("OWNER-06","Cutover rollback window and success thresholds","No cutover or dual writes", "cutover"),
    ]
    put("docs/architecture/owner-decisions.json", {"schema_version":"1.0.0", "decisions":[{
        "id":key,"choice":choice,"status":"unresolved","phase0_default":default,"blocks":gate,
        "approval_evidence":None} for key,choice,default,gate in decisions]})
    gates = [
        ("C-01",1,"100 concurrent PostgreSQL contenders yield exactly one live claim/run and owner", "tests/concurrency/acceptance.py:assert_hundred_contenders"),
        ("C-02",1,"Expired/stale fence rejects renew and complete without mutation; new claim has larger version", "tests/concurrency/acceptance.py:assert_lease_recovery"),
        ("C-03",1,"Dead executor lease expires; recovery resumes only unfinished stages", "tests/concurrency/acceptance.py:assert_lease_recovery"),
        ("C-04",1,"Capability mismatch excludes only the incompatible executor/work pair", "tests/contract/test_behavior.py"),
        ("C-05",1,"Every stage boundary preserves verified result hashes across crash", "db/tests/phase1_assertions.sql"),
        ("C-06",1,"Approval expiry/revocation and maintenance win racing claims/effects", "db/functions/claim_work.md"),
        ("C-07",1,"No claim or run survives rollback of its transaction alone", "db/tests/phase1_assertions.sql"),
        ("API-01",1,"Every registered operation enforces authorization and sensitivity scope", "docs/operations/API.md"),
        ("API-02",1,"Same idempotency key/hash replays; different bytes conflict without duplicate effects", "docs/operations/API.md"),
        ("API-03",1,"Expected version conflict is atomic with audit and outbox", "docs/operations/API.md"),
        ("EV-01",1,"Commit then consumer crash retains durable outbox and later executes once logically", "docs/operations/EVENTS_AND_PROVIDERS.md"),
        ("EV-02",1,"Provider success then persistence failure reconciles without blind resend", "tests/contract/test_behavior.py"),
        ("EV-03",1,"Duplicate and out-of-order webhook events cannot repeat effects or regress success", "docs/operations/EVENTS_AND_PROVIDERS.md"),
        ("SEM-01",1,"Invalid/stale/conflicting proposal siblings are isolated; dependent siblings blocked", "tests/contract/test_behavior.py"),
        ("SEM-02",1,"Restart reuses verified proposal/committed item evidence without reinterpretation", "tests/contract/test_behavior.py"),
        ("TASK-01",1,"Independent task; staged human/semantic/provider/approval fulfillment without duplicate obligation", "docs/architecture/MODEL.md"),
        ("TASK-02",1,"Concurrent dependency cycle creation rejected; recurrence handles DST gaps/folds and updates", "docs/architecture/MODEL.md"),
        ("MEM-01",1,"Memory activation compare-and-swap yields one head; previous versions immutable", "docs/operations/MEMORY.md"),
        ("MIG-01",1,"Clean PostgreSQL install, repeat migration, drift rejection, rollback and forward correction", "scripts/migrations.py"),
        ("REST-01",1,"Corrupt package rejected; clean standard PostgreSQL restore verifies counts/hashes/API synthetic claim", "docs/recovery/RESTORE.md"),
        ("PORT-01",2,"Replacement AI with bootstrap package alone completes governed synthetic operation", "docs/operations/MEMORY.md"),
        ("SURFACE-01",2,"Online Ada transaction/readback/audit and HOME-01 use same operations contract", "docs/PHASE1_MANIFEST.json"),
        ("INTEGRITY-01",2,"Deterministic reversible repair detects seeded defect and proves readback", "db/views/contracts.md"),
        ("WATCH-01",2,"Withheld heartbeat triggers real independent alert; external monitor sees DB-host outage", "docs/operations/WATCHDOG.md"),
        ("SHADOW-01",3,"Dashboard degraded-source behavior, 41/41 renderer bindings and forecast parity proven", "contracts/migration/worker-dispositions.json"),
        ("MIG-02",4,"Typed import/quarantine resolves duplicates/drift with zero unclassified errors", "docs/migration/QUARANTINE.md"),
    ]
    put("tests/acceptance-catalog.json", {"schema_version":"1.0.0", "gates":[{
        "id":id_, "required_phase":phase,"assertion":assertion,"acceptance_reference":reference,
        "status":"pending_integration", "reason":"No Phase 1 PostgreSQL implementation or authorized live environment in Phase 0"
    } for id_,phase,assertion,reference in gates]})
    steps = [
        ("P1-01",[],"Migration executor, roles and schema ledger",["db/migrations","scripts/migrations.py"],["MIG-01"]),
        ("P1-02",["P1-01"],"Typed business and work model; identity aliases and invariant constraints",["db/schemas/model.json","docs/architecture/MODEL.md"],["TASK-01","TASK-02"]),
        ("P1-03",["P1-02"],"Atomic claims, gates, fences, renewal, stage evidence and recovery",["db/functions/claim_work.md"],["C-01","C-02","C-03","C-04","C-05","C-06","C-07"]),
        ("P1-04",["P1-02"],"Durable audit/event/outbox and provider commands with simulated adapters",["contracts/events","contracts/providers"],["EV-01","EV-02","EV-03"]),
        ("P1-05",["P1-03","P1-04"],"Operations API authorization/idempotency and semantic proposal commits",["contracts/api/openapi.json","contracts/operations","contracts/semantic"],["API-01","API-02","API-03","SEM-01","SEM-02"]),
        ("P1-06",["P1-05"],"Memory head/version governance and scoped bootstrap retrieval",["contracts/memory"],["MEM-01"]),
        ("P1-07",["P1-06"],"Portable logical export, clean-room restore and synthetic conformance",["contracts/recovery","docs/recovery/RESTORE.md"],["REST-01"]),
    ]
    put("docs/PHASE1_MANIFEST.json", {"schema_version":"1.0.0", "phase0_repository":"C:\\ECOS\\ecos-2x",
        "repository_path_is_development_record_not_runtime_dependency":True, "phase0_status":"built_contract_foundation",
        "operational_system_maturity":"designed", "baseline_signoff":"pending owner review; no approval fabricated",
        "production_authority":"ECOS 1.x", "provisioning_authorized_by_phase0":False,
        "steps":[{"id":id_,"depends_on":deps,"deliverable":desc,"contracts":contracts,"acceptance_gates":tests,"status":"not_started"} for id_,deps,desc,contracts,tests in steps],
        "phase1_exit":"All Phase 1 catalog gates pass on clean standard PostgreSQL; skipped gates fail the release gate",
        "later_phase_gates":[g[0] for g in gates if g[1] > 1],
        "owner_decisions":"docs/architecture/owner-decisions.json"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    build()
    for name, data in DATA.items():
        path = ROOT / name
        content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        if args.check:
            if path.read_text(encoding="utf-8") != content:
                raise SystemExit("Foundation registry drift: " + name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
    print(f"{'Verified' if args.check else 'Generated'} {len(DATA)} foundation registries")
