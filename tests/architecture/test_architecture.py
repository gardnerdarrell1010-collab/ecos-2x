import hashlib
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads((ROOT/path).read_text(encoding="utf-8"))


class ArchitectureTests(unittest.TestCase):
    def test_exact_review_worker_inventory_and_lossless_source_rows(self):
        registry = read("contracts/migration/worker-dispositions.json")
        rows = registry["workers"]
        expected = {f"TASK-AUTO-{n:06d}" for n in range(1,55)} | {"TASK-AUTO-000029-B"}
        self.assertEqual(len(rows),55)
        self.assertEqual({r["legacy_worker_id"] for r in rows},expected)
        self.assertEqual(len({r["legacy_worker_id"] for r in rows}),55)
        appendix = (ROOT/"docs/baseline/ECOS_2X_WORKER_DISPOSITION_APPENDIX.md").read_bytes()
        self.assertEqual(registry["source_sha256"],hashlib.sha256(appendix).hexdigest())
        lines = appendix.decode("utf-8").splitlines()
        for row in rows:
            actual = [c.strip() for c in lines[row["source_line"]-1].strip("|").split("|")]
            self.assertEqual(row["source_row"],actual)
        self.assertEqual({r["legacy_short_id"] for r in rows if r["retired_at_review"]},{"A017","A030","A034"})
        for key in ("A023","A053","A054","A026","A029-B","A022","A044","A010","A027","A028","A017","A030"):
            self.assertTrue(next(r for r in rows if r["legacy_short_id"] == key)["subordinate_preservation"])
        self.assertEqual(registry["usage"],"migration_and_acceptance_only")

    def test_baseline_hashes_remain_intact(self):
        provenance = read("docs/architecture/baseline-provenance.json")
        self.assertFalse(provenance["fresh_production_read_performed"])
        self.assertEqual(len(provenance["sources"]),2)
        for source in provenance["sources"]:
            self.assertEqual(hashlib.sha256((ROOT/source["path"]).read_bytes()).hexdigest(),source["sha256"])

    def test_all_required_families_mapped_once(self):
        required = {"Contacts","Organizations","Relationships","Projects","Tasks","Communications",
            "Notification Queue","Notification Deliveries","Artifacts","Authoritative Files","Facts","Settings",
            "Validation Lists","Workflow Dependencies","Task Loop","Run Control","Staging Records","Integrity Checks",
            "Ingestion State","Forecast Data Audit","Forecast Performance","AI Memory","Recovery Map","Ingestion Log",
            "Activity Log","Exceptions","System Bootstrap","Sheet Registry","Command Registry","Data Dictionary"}
        rows = read("contracts/migration/legacy-mapping.json")["families"]
        self.assertEqual({r["source_family"] for r in rows},required)
        self.assertEqual(len(rows),len(required))

    def test_required_adr_sections_and_unresolved_owner_choices(self):
        for number in range(1,17):
            text = (ROOT/f"docs/adr/ADR-{number:03d}.md").read_text(encoding="utf-8")
            for heading in ("Status","Context","Decision","Rationale","Alternatives considered","Consequences","Portability impact","Acceptance implications"):
                self.assertIn("**"+heading+":**",text)
        decisions = read("docs/architecture/owner-decisions.json")["decisions"]
        self.assertEqual(len(decisions),6)
        self.assertTrue(all(d["status"]=="unresolved" and d["approval_evidence"] is None for d in decisions))

    def test_lifecycle_edges_and_no_succeeded_work_reopen(self):
        vocabulary = read("config/vocabulary.json")["states"]
        transitions = read("config/lifecycle-transitions.json")["transitions"]
        for name, edges in transitions.items():
            self.assertEqual(set(edges),set(vocabulary[name]))
            self.assertTrue(all(set(targets)<=set(vocabulary[name]) for targets in edges.values()))
        self.assertEqual(transitions["work_occurrence"]["succeeded"],[])
        self.assertIn("revoked",vocabulary["approval"])

    def test_provider_and_capability_registry_boundaries(self):
        rows = read("contracts/providers/boundaries.json")["providers"]
        self.assertEqual(len({r["provider_id"] for r in rows}),10)
        self.assertTrue(all(r["phase0_effects_allowed"] is False for r in rows))
        capabilities = read("config/capabilities.json")
        names = [c["name"] for c in capabilities["capabilities"]]
        self.assertEqual(len(names),len(set(names)))
        self.assertFalse(capabilities["hybrid_is_surface"])
        self.assertTrue(all("chatgpt" not in n and "a053" not in n for n in names))

    def test_api_endpoints_match_operations_and_have_auth(self):
        api = read("contracts/api/openapi.json")
        operations = read("contracts/operations/registry.json")["operations"]
        self.assertEqual(api["openapi"],"3.1.1")
        self.assertEqual(api["security"],[{"bearerAuth":[]}])
        self.assertEqual(set(api["paths"]),{"/v1/operations/"+op["name"] for op in operations})
        for op in operations:
            endpoint = api["paths"]["/v1/operations/"+op["name"]]["post"]
            self.assertEqual(endpoint["requestBody"]["content"]["application/json"]["schema"]["$ref"],op["request_schema"])
            self.assertEqual(endpoint["responses"]["200"]["content"]["application/json"]["schema"]["$ref"],op["response_schema"])
            self.assertTrue({"400","401","403","409","500"} <= set(endpoint["responses"]))

    def test_phase1_manifest_dependency_graph_and_gate_references(self):
        manifest = read("docs/PHASE1_MANIFEST.json")
        self.assertEqual(manifest["operational_system_maturity"],"designed")
        self.assertFalse(manifest["provisioning_authorized_by_phase0"])
        catalog = read("tests/acceptance-catalog.json")["gates"]
        known_gates = {g["id"] for g in catalog}
        covered = set()
        done = set()
        for step in manifest["steps"]:
            self.assertTrue(set(step["depends_on"]) <= done)
            self.assertTrue(set(step["acceptance_gates"]) <= known_gates)
            for file in step["contracts"]:
                self.assertTrue((ROOT/file).exists(),file)
            covered.update(step["acceptance_gates"])
            done.add(step["id"])
        self.assertEqual(covered,{g["id"] for g in catalog if g["required_phase"]==1})
        for gate in catalog:
            self.assertTrue((ROOT/gate["acceptance_reference"].split(":")[0]).exists())
