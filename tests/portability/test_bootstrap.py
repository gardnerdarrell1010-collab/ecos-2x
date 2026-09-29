import unittest
from pathlib import Path

from ecos.core.bootstrap import verify_bootstrap
from ecos.core.contracts import ContractStore
from tests.fixtures import bootstrap, rehash

ROOT = Path(__file__).resolve().parents[2]


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.store = ContractStore(ROOT)
        self.package = bootstrap(self.store)

    def test_package_carries_operations_and_transitive_schemas_offline(self):
        self.assertGreater(verify_bootstrap(self.package,self.store),3)

    def test_missing_operation_schema_and_tampered_context_fail(self):
        self.package["schema_bundle"] = [e for e in self.package["schema_bundle"]
            if e["schema_id"] != self.package["operation_schema_ids"][0]]
        with self.assertRaises(ValueError):
            verify_bootstrap(rehash(self.package),self.store)
        self.package = bootstrap(self.store)
        self.package["context_records"][0]["record"]["title"] = "Changed content"
        with self.assertRaises(ValueError):
            verify_bootstrap(rehash(self.package),self.store)

    def test_tampered_schema_hash_fails(self):
        self.package["schema_bundle"][0]["sha256"] = "f"*64
        with self.assertRaises(ValueError):
            verify_bootstrap(rehash(self.package),self.store)
