import hashlib
import tempfile
import unittest
from pathlib import Path

from ecos.core.contracts import ContractStore
from ecos.core.export_verify import verify_inventory
from tests.fixtures import specimen

ROOT = Path(__file__).resolve().parents[2]


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root/"restore.md").write_bytes(b"Synthetic restore instructions\n")
        (self.root/"verify.sql").write_bytes(b"select 1;\n")
        store = ContractStore(ROOT)
        self.manifest = specimen(store.schemas["https://contracts.ecos.invalid/v1/export_manifest.schema.json"],store)
        self.manifest["files"] = [{"path":p.name,"size_bytes":len(p.read_bytes()),
            "sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"record_count":None,
            "role":"restore_instructions" if p.suffix==".md" else "verification_queries"} for p in sorted(self.root.iterdir())]
        self.manifest["restore_instructions_path"] = "restore.md"
        self.manifest["verification_queries_path"] = "verify.sql"
        store.validate("export_manifest",self.manifest)

    def test_inventory_checksums_and_readonly_verification(self):
        self.assertEqual(verify_inventory(self.root,self.manifest),2)
        self.assertEqual(verify_inventory(self.root,self.manifest),2)

    def test_bitflip_size_and_missing_file_fail(self):
        (self.root/"verify.sql").write_bytes(b"select 2;\n")
        with self.assertRaises(ValueError):
            verify_inventory(self.root,self.manifest)
        (self.root/"verify.sql").unlink()
        with self.assertRaises(FileNotFoundError):
            verify_inventory(self.root,self.manifest)

    def test_traversal_absolute_and_case_collision_fail(self):
        for path in ("../outside", "/outside", "C:/outside", "nested\\file", "./restore.md"):
            manifest = self.manifest | {"files":[self.manifest["files"][0] | {"path":path}]}
            with self.subTest(path=path), self.assertRaises(ValueError):
                verify_inventory(self.root,manifest)
        manifest = self.manifest | {"files":self.manifest["files"]+[self.manifest["files"][0] | {"path":"RESTORE.MD"}]}
        with self.assertRaises(ValueError):
            verify_inventory(self.root,manifest)

    def test_restore_paths_must_be_in_manifest(self):
        with self.assertRaises(ValueError):
            verify_inventory(self.root,self.manifest | {"verification_queries_path":"missing.sql"})
