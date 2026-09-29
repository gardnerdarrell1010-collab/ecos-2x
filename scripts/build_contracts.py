"""Generate portable v1 schemas; this file is the editable schema source.

No connections or database effects. --check compares without writing.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://contracts.ecos.invalid/v1/"
DRAFT = "https://json-schema.org/draft/2020-12/schema"
OUTPUTS: dict[str, dict] = {}


def obj(properties, required=None, **extra):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required,
            "additionalProperties": False, **extra}


def arr(items, minimum=0, unique=False):
    return {"type": "array", "items": items, "minItems": minimum, "uniqueItems": unique}


def enum(*values):
    return {"type": "string", "enum": list(values)}


def ref(name):
    return {"$ref": BASE + name + ".schema.json"}


def nullable(spec):
    return {"anyOf": [spec, {"type": "null"}]}


def emit(path, value):
    OUTPUTS[path] = value


def schema(group, name, properties, required=None, **extra):
    body = obj(properties, required, **extra)
    emit(f"contracts/{group}/{name}.schema.json",
         {"$schema": DRAFT, "$id": BASE + name + ".schema.json", "title": name, **body})
    return ref(name)


TEXT = {"type": "string", "minLength": 1, "maxLength": 10000}
TOKEN = {"type": "string", "pattern": "^[a-z][a-z0-9_.-]{0,127}$"}
UUID = {"type": "string", "format": "uuid"}
TIME = {"type": "string", "format": "date-time"}
HASH = {"type": "string", "pattern": "^[a-f0-9]{64}$"}
BOOL = {"type": "boolean"}
NAT = {"type": "integer", "minimum": 0}
POS = {"type": "integer", "minimum": 1}
KEY = {"type": "string", "minLength": 1, "maxLength": 200}
VERSION = {"const": "1.0.0"}
VOCAB = {
    "task_lifecycle": "draft open waiting completed cancelled",
    "task_wait_reason": "none dependency owner external approval scheduled",
    "approval": "pending approved rejected changes_requested expired revoked",
    "work_occurrence": "pending ready claimed running succeeded retry_wait failed dead_lettered cancelled",
    "delivery": "planned ready held sending delivered failed acknowledged cancelled",
    "provider_outcome": "pending accepted succeeded failed unknown_outcome reconciled",
    "maturity": "designed built end_to_end_verified shadow_verified production_verified",
    "claim": "active released expired revoked",
    "outbox": "pending claimed delivered retry_wait dead_lettered cancelled",
    "execution_run": "started succeeded failed abandoned cancelled",
    "proposal": "created validated partially_committed committed rejected conflicted",
    "proposal_item": "valid committed invalid stale conflicting ambiguous blocked",
    "communication_processing": "pending ready running succeeded retry_wait failed dead_lettered",
    "availability": "available degraded unavailable unknown",
    "sensitivity": "public internal confidential restricted",
    "quarantine": "received invalid identity_unresolved validated transformed promoted excluded",
    "migration_classification": "MIGRATE MIGRATE_CURRENT_STATE ARCHIVE_REFERENCE REBUILD RETIRE",
    "backup_kind": "managed_pitr logical_postgresql portable_ecos_export",
    "restore_state": "pending running passed failed",
    "stage_kind": "human deterministic semantic provider approval",
    "execution_surface": "DATABASE_DETERMINISTIC RESIDENT_DETERMINISTIC_PROVIDER ONLINE_SEMANTIC INTERACTIVE_ADA",
}


def state(name):
    return {"$ref": BASE + "vocabulary.schema.json#/$defs/" + name}


def entity(group, name, fields, immutable=False, **extra):
    common = {"id": UUID, "schema_version": VERSION, "created_at": TIME}
    if not immutable:
        common["record_version"] = POS
    return schema(group, name, common | fields, **extra)


def build():
    emit("config/vocabulary.json", {"schema_version": "1.0.0", "states": {k: v.split() for k, v in VOCAB.items()}})
    emit("contracts/common/vocabulary.schema.json", {"$schema": DRAFT,
        "$id": BASE + "vocabulary.schema.json", "$defs": {k: enum(*v.split()) for k, v in VOCAB.items()}})
    source = schema("common", "source_reference", {
        "record_type": TOKEN, "record_id": UUID, "record_version": POS,
        "content_hash": HASH, "authority": enum("structured_ecos", "provider", "governed_memory", "conversation_evidence"),
    })
    evidence = schema("common", "evidence", {
        "source": source, "assertion": TEXT, "verification": enum("verified", "unverified", "conflicting"),
    })
    expected = obj({"record_type": TOKEN, "record_id": UUID, "record_version": POS})
    fence = schema("operations", "fence", {
        "occurrence_id": UUID, "stage_definition_id": UUID, "claim_id": UUID,
        "claim_version": POS, "fence_token": UUID, "executor_instance_id": UUID,
    })
    context = schema("operations", "request_context", {
        "principal_id": UUID, "executor_instance_id": nullable(UUID), "correlation_id": UUID,
        "causation_id": nullable(UUID), "idempotency_key": KEY,
    })
    override = schema("work", "priority_override", {
        "value": {"type": "integer", "minimum": -100, "maximum": 100}, "actor_id": UUID,
        "reason_code": TOKEN, "created_at": TIME, "expires_at": TIME,
    })
    entity("task", "task", {"business_id": KEY, "title": TEXT, "project_id": nullable(UUID),
        "lifecycle_state": state("task_lifecycle"), "wait_reason": state("task_wait_reason"),
        "description": TEXT}, allOf=[{
            "if": {"properties": {"lifecycle_state": {"const": "waiting"}}},
            "then": {"properties": {"wait_reason": {"not": {"const": "none"}}}},
            "else": {"properties": {"wait_reason": {"const": "none"}}},
        }])
    entity("task", "task_assignment", {"task_id": UUID, "party_id": UUID,
        "role": enum("owner", "delegate", "reviewer"), "effective_from": TIME, "effective_to": nullable(TIME)})
    entity("task", "task_schedule", {"task_id": UUID, "due_at": nullable(TIME), "follow_up_at": nullable(TIME),
        "planned_start_at": nullable(TIME), "timezone": TEXT, "rrule": nullable(TEXT),
        "dst_gap_policy": enum("skip", "next_valid"), "dst_fold_policy": enum("earlier", "later"),
        "recurrence_anchor": enum("fixed_calendar", "completion_relative", "none")})
    entity("task", "task_dependency", {"task_id": UUID, "prerequisite_task_id": UUID,
        "satisfaction_rule": enum("completed", "approved_evidence")})
    entity("task", "approval_request", {"task_id": nullable(UUID), "subject_type": TOKEN,
        "subject_id": UUID, "subject_hash": HASH, "state": state("approval"), "expires_at": TIME})
    entity("task", "approval_decision", {"approval_request_id": UUID, "decision": enum("approved", "rejected", "changes_requested", "expired", "revoked"),
        "actor_id": UUID, "reason_code": TOKEN, "evidence": arr(evidence),
        "supersedes_decision_id": nullable(UUID)}, immutable=True)
    entity("task", "task_evidence", {"task_id": UUID, "evidence": evidence}, immutable=True)
    entity("work", "work_definition", {"name": TOKEN, "definition_version": POS,
        "enabled": BOOL, "fulfillment_kind": enum("single_stage", "staged"), "retry_policy_id": UUID})
    entity("work", "work_stage_definition", {"work_definition_id": UUID, "stage_key": TOKEN,
        "kind": state("stage_kind"), "execution_surface": state("execution_surface"),
        "input_schema_id": TEXT, "result_schema_id": TEXT, "requires_approval": BOOL})
    entity("work", "work_occurrence", {"work_definition_id": UUID, "stage_definition_id": UUID,
        "fulfillment_id": UUID, "task_id": nullable(UUID), "state": state("work_occurrence"),
        "occurrence_key": KEY, "due_at": TIME, "retry_at": nullable(TIME),
        "ready_override_at": nullable(TIME), "priority_override": nullable(override),
        "claim_version": NAT, "attempt_count": NAT})
    entity("work", "work_dependency", {"occurrence_id": UUID, "prerequisite_occurrence_id": UUID,
        "required_result_schema_id": TEXT, "required_result_hash": nullable(HASH)})
    entity("work", "work_claim", {"occurrence_id": UUID, "stage_definition_id": UUID,
        "executor_instance_id": UUID, "claim_version": POS, "fence_token": UUID,
        "state": state("claim"), "acquired_at": TIME, "expires_at": TIME, "renewed_at": TIME})
    selection = schema("work", "selection_evidence", {"policy_version": {"const": "lexicographic-v1"},
        "evaluated_at": TIME, "source_versions": arr(expected), "eligible": BOOL,
        "reason_codes": arr(TOKEN), "priority_override": {"type": "integer", "minimum": -100, "maximum": 100},
        "immediate_ready": BOOL, "sla_breach_seconds": NAT, "deadline_pressure_seconds": NAT,
        "business_impact": {"type": "integer", "minimum": 0, "maximum": 100},
        "recurrence_relative_age_basis_points": NAT, "created_at": TIME, "occurrence_id": UUID})
    entity("work", "execution_run", {"fence": fence, "state": state("execution_run"),
        "selection_evidence": selection, "correlation_id": UUID, "ended_at": nullable(TIME)})
    entity("work", "stage_result", {"occurrence_id": UUID, "stage_definition_id": UUID,
        "execution_run_id": UUID, "result_schema_id": TEXT, "content_hash": HASH,
        "artifact_uri": TEXT, "verified_at": TIME, "verified_by": UUID, "source_references": arr(source)}, immutable=True)
    entity("work", "retry_policy", {"max_attempts": POS, "initial_delay_seconds": POS,
        "max_delay_seconds": POS, "backoff_multiplier": POS, "jitter_basis_points": {"type": "integer", "minimum": 0, "maximum": 10000},
        "retryable_error_classes": arr(TOKEN, unique=True)})
    entity("work", "dead_letter_item", {"occurrence_id": UUID, "reason_code": TOKEN,
        "last_run_id": UUID, "reviewed_by": nullable(UUID), "resolution_event_id": nullable(UUID)})
    entity("capabilities", "executor", {"name": TOKEN, "surface": state("execution_surface"), "enabled": BOOL})
    entity("capabilities", "executor_instance", {"executor_id": UUID, "boot_id": UUID,
        "availability": state("availability"), "principal_id": UUID})
    entity("capabilities", "capability", {"name": TOKEN, "version": POS, "description": TEXT})
    entity("capabilities", "executor_capability", {"executor_instance_id": UUID, "capability_name": TOKEN,
        "capability_version": POS, "attested_by": UUID, "expires_at": TIME})
    entity("capabilities", "stage_capability_requirement", {"stage_definition_id": UUID,
        "capability_name": TOKEN, "minimum_version": POS})
    entity("capabilities", "heartbeat", {"executor_instance_id": UUID, "observed_at": TIME,
        "received_at": TIME, "valid_until": TIME, "availability": state("availability"),
        "evidence_hash": HASH}, immutable=True)

    transitions = {
        "task.transition": obj({"task_id": UUID, "expected_version": POS,
            "target_state": state("task_lifecycle"), "wait_reason": state("task_wait_reason"),
            "reason_code": TOKEN, "evidence": arr(evidence)}),
        "task.evidence.attach": obj({"task_id": UUID, "expected_version": POS, "evidence": evidence}),
        "fact.record": obj({"subject_id": UUID, "statement": TEXT, "source_references": arr(source, 1),
            "sensitivity": state("sensitivity")}),
    }
    proposal_operation = {"oneOf": [obj({"operation": {"const": name}, "arguments": args})
                                     for name, args in transitions.items()]}
    proposal_item = schema("semantic", "proposal_item", {"item_id": UUID,
        "depends_on_item_ids": arr(UUID, unique=True), "source_references": arr(source, 1),
        "expected_record_versions": arr(expected, 1), "proposed_operations": arr(proposal_operation, 1),
        "evidence": arr(evidence, 1), "confidence_basis_points": nullable({"type": "integer", "minimum": 0, "maximum": 10000}),
        "unresolved_ambiguity": arr(TEXT)})
    schema("semantic", "semantic_proposal", {"id": UUID, "proposal_type": TOKEN,
        "schema_version": VERSION, "created_at": TIME, "correlation_id": UUID,
        "source_references": arr(source, 1), "expected_record_versions": arr(expected, 1),
        "items": arr(proposal_item, 1), "content_hash": HASH})
    schema("semantic", "proposal_commit_result", {"proposal_id": UUID, "proposal_hash": HASH,
        "schema_version": VERSION, "correlation_id": UUID,
        "items": arr(obj({"item_id": UUID, "state": state("proposal_item"), "reason_code": TOKEN,
            "committed_event_ids": arr(UUID), "result_hash": nullable(HASH)}), 1)})

    event_fields = {"id": UUID, "event_type": TOKEN, "schema_version": VERSION,
        "aggregate_type": TOKEN, "aggregate_id": UUID, "correlation_id": UUID,
        "causation_id": nullable(UUID), "created_at": TIME}
    domain_payload = {"oneOf": [obj({"operation": {"const": name}, "arguments": args, "record_version": POS})
                                for name, args in transitions.items()]}
    domain_types = {"task.transition":"task.transitioned", "task.evidence.attach":"task.evidence_attached", "fact.record":"fact.recorded"}
    schema("events", "domain_event", event_fields | {"event_type":enum(*domain_types.values()), "payload": domain_payload},
        allOf=[{"if":{"properties":{"event_type":{"const":event_type}}},
                "then":{"properties":{"aggregate_type":{"const":"fact" if name == "fact.record" else "task"},
                                       "payload":{"properties":{"operation":{"const":name}}}}}}
               for name,event_type in domain_types.items()])
    schema("events", "execution_event", event_fields | {"event_type":enum("execution.started","execution.succeeded","execution.failed","execution.abandoned","execution.cancelled"), "payload": obj({"execution_run_id": UUID,
        "occurrence_id": UUID, "state": state("execution_run"), "reason_code": TOKEN,
        "fence": fence, "evidence_hash": nullable(HASH)})})
    entity("events", "outbox_item", {"domain_event_id": UUID, "provider_command_id": nullable(UUID),
        "destination": TOKEN, "state": state("outbox"), "idempotency_key": KEY,
        "available_at": TIME, "attempt_count": NAT, "lease_expires_at": nullable(TIME), "correlation_id": UUID})
    entity("providers", "provider_command", {"provider": TOKEN, "account_scope": KEY,
        "command_type": TOKEN, "idempotency_key": KEY, "request_schema_id": TEXT,
        "request_artifact_uri": TEXT, "request_hash": HASH, "correlation_id": UUID,
        "causation_id": UUID, "outcome": state("provider_outcome"),
        "reconciliation_strategy": enum("native_idempotency", "provider_lookup", "manual_only"),
        "approval_request_id": nullable(UUID)})
    entity("providers", "provider_attempt", {"provider_command_id": UUID, "attempt_number": POS,
        "request_hash": HASH, "started_at": TIME, "completed_at": nullable(TIME),
        "provider_request_id": nullable(KEY), "response_hash": nullable(HASH),
        "error_class": nullable(enum("transient_proven_no_effect", "permanent", "ambiguous")),
        "outcome": state("provider_outcome")}, immutable=True)
    entity("providers", "provider_result", {"provider_command_id": UUID, "provider_attempt_id": UUID,
        "outcome": state("provider_outcome"), "provider_object_id": nullable(KEY),
        "observed_at": TIME, "evidence_hash": HASH, "reconciled_outcome": nullable(enum("succeeded", "failed", "no_effect"))}, immutable=True,
        allOf=[{"if":{"properties":{"outcome":{"const":"reconciled"}}},
                "then":{"properties":{"reconciled_outcome":enum("succeeded","failed","no_effect")}},
                "else":{"properties":{"reconciled_outcome":{"type":"null"}}}}])
    entity("providers", "provider_receipt", {"provider": TOKEN, "account_scope": KEY,
        "provider_event_id": nullable(KEY), "dedupe_key": KEY, "provider_object_id": nullable(KEY),
        "provider_occurred_at": TIME, "received_at": TIME, "raw_artifact_uri": TEXT,
        "raw_content_hash": HASH, "signature_verified": BOOL, "correlation_id": UUID}, immutable=True)
    entity("communications", "communication", {"receipt_id": UUID, "channel": enum("email", "sms", "calendar", "review"),
        "provider_thread_id": nullable(KEY), "direction": enum("inbound", "outbound"),
        "sender_party_id": nullable(UUID), "body_artifact_uri": TEXT, "body_hash": HASH})
    entity("communications", "communication_processing", {"communication_id": UUID,
        "source_version": POS, "state": state("communication_processing"), "occurrence_id": UUID,
        "proposal_id": nullable(UUID), "committed_result_id": nullable(UUID)})
    entity("communications", "notification", {"business_reason_code": TOKEN, "subject_type": TOKEN,
        "subject_id": UUID, "content_artifact_uri": TEXT, "content_hash": HASH, "policy_version": POS})
    entity("communications", "delivery", {"notification_id": UUID, "recipient_party_id": UUID,
        "channel": enum("email", "sms"), "destination_reference": KEY, "policy_key": KEY,
        "state": state("delivery"), "approval_request_id": nullable(UUID), "provider_command_id": nullable(UUID)})
    entity("communications", "delivery_attempt", {"delivery_id": UUID, "provider_attempt_id": UUID,
        "provider_message_id": nullable(KEY), "evidence_hash": HASH, "provider_status_at": TIME}, immutable=True)

    entity("memory", "memory_scope", {"scope_type": TOKEN, "scope_id": UUID,
        "sensitivity": state("sensitivity"), "authorized_role_names": arr(TOKEN, 1, True)})
    entity("memory", "memory_record", {"business_id": KEY, "scope_id": UUID,
        "memory_kind": TOKEN, "active_head_version_id": nullable(UUID)})
    entity("memory", "memory_version", {"memory_record_id": UUID, "version_number": POS,
        "supersedes_version_id": nullable(UUID), "scope_id": UUID, "statement": TEXT,
        "operational_meaning": TEXT, "provenance": arr(source, 1), "effective_at": TIME,
        "sensitivity": state("sensitivity"), "retention_policy_ref": KEY,
        "authoritative_references": arr(source, 1), "content_hash": HASH,
        "compaction_run_id": nullable(UUID)}, immutable=True)
    entity("memory", "memory_reference", {"memory_version_id": UUID, "source": source,
        "relationship": enum("supports", "qualifies", "contradicts")}, immutable=True)
    entity("memory", "memory_compaction_run", {"scope_id": UUID, "input_version_ids": arr(UUID, 1),
        "output_version_id": UUID, "source_references": arr(source, 1),
        "omitted_reference_ids": arr(UUID), "reason_codes": arr(TOKEN), "manifest_hash": HASH,
        "verifier_id": UUID, "contradictions_resolved": BOOL}, immutable=True)
    schema("memory", "bootstrap_package", {"package_id": UUID, "schema_version": VERSION,
        "database_schema_version": TEXT, "generated_at": TIME, "principal_id": UUID,
        "sensitivity_ceiling": state("sensitivity"), "governed_context": arr(source),
        "context_records": arr(obj({"source":source,"record_schema_id":TEXT,"record":{"type":"object"}})),
        "active_memory_heads": arr(ref("memory_version")), "unresolved_exceptions": arr(source),
        "operation_schema_ids": arr(TEXT, 1), "capability_vocabulary": arr(TOKEN, 1, True),
        "operation_bindings": arr(obj({"operation":TOKEN,"path":TEXT,"request_schema_id":TEXT,"response_schema_id":TEXT}),1),
        "schema_bundle": arr(obj({"schema_id":TEXT,"sha256":HASH,"document":{
            "type":"object","required":["$schema","$id"],"properties":{"$schema":{"const":DRAFT},"$id":TEXT}}}),1),
        "relevant_work": arr(ref("work_occurrence")), "content_hash": HASH})

    file_entry = obj({"path": {"type": "string", "pattern": "^(?!/)(?!.*(?:^|/)\\.\\.(?:/|$))(?!.*[\\\\:]).+$"},
        "size_bytes": NAT, "sha256": HASH, "record_count": nullable(NAT),
        "role": enum("schema", "data", "contracts", "memory", "provider_inventory", "restore_instructions", "verification_queries", "migration", "configuration")})
    schema("recovery", "export_manifest", {"package_id": UUID, "schema_version": VERSION,
        "created_at": TIME, "database_schema_version": TEXT, "migration_head": TEXT,
        "postgresql_version": TEXT, "tool_versions": obj({"pg_dump": TEXT, "exporter": TEXT}),
        "files": arr(file_entry, 1), "memory_head_ids": arr(UUID),
        "restore_instructions_path": TEXT, "verification_queries_path": TEXT,
        "secret_reference_names": arr(TOKEN, unique=True), "plaintext_secrets_included": {"const": False},
        "storage_control": {"const": "darrell_controlled"}})
    entity("recovery", "backup_record", {"kind": state("backup_kind"), "started_at": TIME,
        "completed_at": TIME, "artifact_uri": TEXT, "manifest_hash": HASH,
        "encrypted": {"const": True}, "recovery_point_at": TIME, "restore_test_id": nullable(UUID)}, immutable=True)
    entity("recovery", "restore_test", {"package_id": UUID, "target_host_class": enum("standard_postgresql", "managed_postgresql"),
        "state": state("restore_state"), "started_at": TIME, "completed_at": nullable(TIME),
        "checks": arr(obj({"check_id": TOKEN, "passed": BOOL, "evidence_hash": HASH}), 1),
        "observed_rpo_seconds": NAT, "observed_rto_seconds": NAT}, immutable=True)

    entity("migration", "raw_migration_batch", {"source_system": KEY, "extracted_at": TIME,
        "source_registry_version": KEY, "artifact_uri": TEXT, "sha256": HASH,
        "row_count": NAT, "column_names": arr(KEY, 1), "source_family": KEY}, immutable=True)
    entity("migration", "quarantine_item", {"batch_id": UUID, "source_locator": KEY,
        "raw_hash": HASH, "legacy_id": nullable(KEY), "source_family": KEY,
        "classification": state("migration_classification"), "state": state("quarantine"),
        "reason_codes": arr(TOKEN), "identity_resolution_id": nullable(UUID),
        "transformation_version": nullable(KEY), "target_id": nullable(UUID)})
    entity("migration", "legacy_identity", {"source_system": KEY, "source_family": KEY,
        "legacy_id": KEY, "source_batch_id": UUID, "source_locator": KEY,
        "target_type": TOKEN, "target_id": UUID, "resolution_evidence_hash": HASH}, immutable=True)

    operations = dict(transitions)
    operations.update({
        "work.claim": obj({"executor_instance_id": UUID, "lease_seconds": {"type": "integer", "minimum": 1, "maximum": 300}}),
        "work.renew": obj({"fence": fence, "lease_seconds": {"type": "integer", "minimum": 1, "maximum": 300}}),
        "work.complete": obj({"fence": fence, "result": ref("stage_result")}),
        "proposal.commit": obj({"proposal": ref("semantic_proposal")}),
        "provider.result.record": obj({"result": ref("provider_result")}),
        "memory.activate": obj({"memory_record_id": UUID, "expected_version": POS, "new_version": ref("memory_version")}),
        "approval.decide": obj({"approval_request_id": UUID, "expected_version": POS,
            "decision": enum("approved", "rejected", "changes_requested"), "subject_hash": HASH, "reason_code": TOKEN}),
    })
    errors = schema("operations", "operation_error", {"code": enum("invalid_contract", "unauthenticated", "forbidden", "stale_version", "invalid_transition", "gate_blocked", "idempotency_conflict", "expired_fence", "unknown_outcome", "internal_error"),
        "message": TEXT, "correlation_id": UUID, "retryable": BOOL})
    generic_result = schema("operations", "operation_result", {"schema_version": VERSION,
        "operation_id": UUID, "correlation_id": UUID, "status": enum("committed", "replayed", "no_candidate"),
        "event_ids": arr(UUID), "record_versions": arr(expected), "result_hash": HASH})
    claim_result = schema("operations", "claim_result", {"schema_version": VERSION, "correlation_id": UUID,
        "claim": nullable(ref("work_claim")), "execution_run": nullable(ref("execution_run"))},
        allOf=[{"if":{"properties":{"claim":{"type":"null"}}},
                "then":{"properties":{"execution_run":{"type":"null"}}},
                "else":{"properties":{"execution_run":{"type":"object"}}}}])
    registry = []
    paths = {}
    for name, args in operations.items():
        request = schema("operations", name + "-request", {"schema_version": VERSION, "context": context, "arguments": args})
        result = ref("proposal_commit_result") if name == "proposal.commit" else claim_result if name in {"work.claim", "work.renew"} else generic_result
        role = "provider_adapter" if name.startswith("provider.") else "executor" if name.startswith("work.") else "owner" if name == "approval.decide" else "operations_api"
        registry.append({"name": name, "request_schema": request["$ref"], "response_schema": result["$ref"],
            "required_role": role, "semantic_proposable": name in transitions,
            "idempotency_scope": "principal_id + operation + idempotency_key",
            "atomicity": "per proposal item and its operations" if name == "proposal.commit" else "single transaction",
            "acceptance_ids": ["API-01", "API-02", "API-03"]})
        paths["/v1/operations/" + name] = {"post": {"operationId": name.replace(".", "_"),
            "summary": "Governed " + name, "requestBody": {"required": True, "content": {"application/json": {"schema": request}}},
            "responses": {"200": {"description": "Committed or replayed result", "content": {"application/json": {"schema": result}}},
                **{str(code): {"description": label, "content": {"application/json": {"schema": errors}}}
                   for code, label in [(400,"Contract violation"),(401,"Unauthenticated"),(403,"Forbidden"),(409,"Conflict or gate failure"),(500,"Unexpected failure")]}}}}
    emit("contracts/operations/registry.json", {"schema_version": "1.0.0", "operations": registry})
    emit("contracts/api/openapi.json", {"openapi": "3.1.1", "info": {"title": "ECOS governed operations", "version": "1.0.0",
        "description": "Contract only; no API server is provisioned by Phase 0."},
        "jsonSchemaDialect": DRAFT, "security": [{"bearerAuth": []}], "paths": paths,
        "components": {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}}}})

    worker_fields = {k: TEXT for k in ["legacy_name", "business_capability", "current_trigger", "current_execution_class",
        "2x_disposition", "2x_trigger", "target_latency", "acceptance_test", "notes"]}
    worker_fields.update({"legacy_worker_id": {"type": "string", "pattern": "^TASK-AUTO-0000[0-5][0-9](-B)?$"},
        "legacy_short_id": {"type": "string", "pattern": "^A[0-9]{3}(-B)?$"},
        "2x_execution_surface": arr(state("execution_surface"), unique=True),
        "semantic_required": enum("yes", "no", "conditional", "upstream_only", "not_applicable"),
        "provider_adapter": arr(TOKEN, unique=True), "proposed_objects": arr(TEXT, 1),
        "retirement_maturity": enum("production_verified", "capability_retired_pending_authority_confirmation"),
        "retirement_conditions": TEXT, "retired_at_review": BOOL,
        "source_row": arr(TEXT, 6), "source_line": POS, "subordinate_preservation": arr(TEXT)})
    schema("migration", "worker_registry", {"schema_version": VERSION, "review_date": {"const": "2026-09-28"},
        "usage": {"const": "migration_and_acceptance_only"}, "source_sha256": HASH,
        "workers": {**arr(obj(worker_fields), 55), "maxItems": 55}})
    schema("providers", "provider_boundaries", {"schema_version": VERSION, "providers": arr(obj({
        "provider_id": TOKEN, "name": TEXT, "authoritative_externally": BOOL, "authority_scope": TEXT,
        "ecos_stores": TEXT, "idempotency_and_reconciliation": TEXT, "portable_replacement": TEXT,
        "secret_storage": TEXT, "phase0_effects_allowed": {"const": False}, "retry_policy": TEXT, "policy_gate": TEXT}), 10)})
    schema("migration", "legacy_mapping", {"schema_version": VERSION, "review_date": TEXT,
        "classifications": arr(state("migration_classification"), 5, True), "source_authority_revalidation": TEXT,
        "families": arr(obj({"source_family": TEXT, "classification": state("migration_classification"),
            "target_objects": arr(TOKEN, 1, True), "rule": TEXT, "identity_key": TEXT, "promotion_gate": TEXT,
            "raw_preservation": TEXT}), 26)})
    emit("db/schemas/model.json", {"schema_version": "1.0.0", "status": "designed", "entities": [
        {"name": value["title"], "schema": value["$id"], "fields": list(value["properties"]),
         "mutable": "record_version" in value["properties"]}
        for path, value in OUTPUTS.items() if path.endswith(".schema.json") and "properties" in value
        and "id" in value["properties"]]})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    build()
    mismatches = []
    for name, value in OUTPUTS.items():
        content = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        path = ROOT / name
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                mismatches.append(name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
    if mismatches:
        raise SystemExit("Generated contract drift: " + ", ".join(mismatches))
    print(f"{'Verified' if args.check else 'Generated'} {len(OUTPUTS)} contract artifacts")


if __name__ == "__main__":
    main()
