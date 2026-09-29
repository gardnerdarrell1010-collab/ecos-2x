import copy
import json
import unittest
from pathlib import Path

from jsonschema import ValidationError

from ecos.core.contracts import ContractStore, canonical_bytes, content_hash
from tests.fixtures import NOW, ZERO_HASH, proposal, specimen, task, uid

ROOT = Path(__file__).resolve().parents[2]


class SchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = ContractStore(ROOT)

    def test_all_schemas_and_references_validate_offline(self):
        self.store.check_references()
        self.assertGreater(len(self.store.schemas), 60)
        for id_, schema in self.store.schemas.items():
            with self.subTest(schema=id_):
                self.store.validate(id_, specimen(schema, self.store))

    def test_task_without_project_is_valid(self):
        self.store.validate("task", task())

    def test_task_rejects_runtime_fields_and_compound_statuses(self):
        for field in ("claim_id", "lease_expires_at", "attempt_count", "dispatch_rank"):
            value = task() | {field: 1}
            with self.subTest(field=field), self.assertRaises(ValidationError):
                self.store.validate("task", value)
        with self.assertRaises(ValidationError):
            self.store.validate("task", task() | {"lifecycle_state":"Completed but waiting on SMS"})

    def test_task_wait_reason_coherence(self):
        for changes in ({"lifecycle_state":"waiting"}, {"wait_reason":"owner"}):
            with self.assertRaises(ValidationError):
                self.store.validate("task", task() | changes)

    def test_uuid_time_version_and_unknown_keys_fail(self):
        for changes in ({"id":"legacy-run-duplicate"},{"created_at":"yesterday"},{"record_version":0},
                        {"record_version":True},{"schema_version":"2.0.0"},{"extra":"unsafe"}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.store.validate("task", task() | changes)

    def test_proposal_contract_and_forbidden_operation(self):
        value = proposal()
        self.store.validate("semantic_proposal", value)
        value["items"][0]["proposed_operations"][0] = {"operation":"sql.execute", "arguments":{"sql":"update task"}}
        with self.assertRaises(ValidationError):
            self.store.validate("semantic_proposal", value)

    def test_hash_order_stable_and_content_tamper_visible(self):
        value = proposal()
        self.assertEqual(content_hash(value), content_hash(dict(reversed(list(value.items())))))
        value["items"][0]["unresolved_ambiguity"].append("changed")
        self.assertNotEqual(value["content_hash"], content_hash(value))
        self.assertEqual(canonical_bytes({"z":True,"a":"é"}), b'{"a":"\xc3\xa9","z":true}')
        for invalid in ({"number":1.2},{"number":float("nan")},{1:"invalid key"}):
            with self.assertRaises(ValueError):
                canonical_bytes(invalid)

    def test_hybrid_is_not_an_execution_surface(self):
        sample = specimen(self.store.schemas["https://contracts.ecos.invalid/v1/work_stage_definition.schema.json"], self.store)
        sample["execution_surface"] = "HYBRID"
        with self.assertRaises(ValidationError):
            self.store.validate("work_stage_definition", sample)

    def test_provider_command_requires_stable_key_and_hash(self):
        value = specimen(self.store.schemas["https://contracts.ecos.invalid/v1/provider_command.schema.json"], self.store)
        del value["idempotency_key"]
        with self.assertRaises(ValidationError):
            self.store.validate("provider_command", value)

    def test_registry_payloads_validate(self):
        for name,path in [("worker_registry","contracts/migration/worker-dispositions.json"),
                          ("legacy_mapping","contracts/migration/legacy-mapping.json"),
                          ("provider_boundaries","contracts/providers/boundaries.json")]:
            self.store.validate(name, json.loads((ROOT / path).read_text(encoding="utf-8")))

    def test_materialized_positive_and_negative_fixtures(self):
        examples = json.loads((ROOT/"db/fixtures/contract-examples.json").read_text(encoding="utf-8"))
        self.assertTrue(examples["synthetic_only"])
        for case in examples["cases"]:
            with self.subTest(name=case["name"]):
                if case["valid"]:
                    self.store.validate(case["schema"],case["payload"])
                else:
                    with self.assertRaises(ValidationError):
                        self.store.validate(case["schema"],case["payload"])

    def test_reconciled_result_requires_explicit_resolution(self):
        value = specimen(self.store.schemas["https://contracts.ecos.invalid/v1/provider_result.schema.json"],self.store)
        value["outcome"] = "reconciled"
        with self.assertRaises(ValidationError):
            self.store.validate("provider_result",value)
        value["reconciled_outcome"] = "no_effect"
        self.store.validate("provider_result",value)

    def test_event_payload_must_match_registered_event_type(self):
        value = specimen(self.store.schemas["https://contracts.ecos.invalid/v1/domain_event.schema.json"],self.store)
        value["event_type"] = "fact.recorded"
        with self.assertRaises(ValidationError):
            self.store.validate("domain_event",value)
