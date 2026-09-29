import ast
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class PortabilityTests(unittest.TestCase):
    def test_core_imports_no_network_database_or_ai_sdk(self):
        forbidden = {"supabase","openai","anthropic","psycopg","requests","httpx","socket","urllib","subprocess"}
        for path in (ROOT/"src").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node,ast.Import):
                    imports = [n.name.split(".")[0] for n in node.names]
                elif isinstance(node,ast.ImportFrom):
                    imports = [(node.module or "").split(".")[0]]
                else:
                    continue
                self.assertFalse(set(imports)&forbidden, path)
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("C:\\ECOS",text)
            self.assertNotIn("TASK-AUTO-",text)

    def test_openapi_references_resolve_from_offline_registry(self):
        from ecos.core.contracts import ContractStore
        store = ContractStore(ROOT)
        api = json.loads((ROOT/"contracts/api/openapi.json").read_text())
        def walk(value):
            if isinstance(value,dict):
                if "$ref" in value:
                    self.assertIn(value["$ref"],store.schemas)
                for child in value.values():
                    walk(child)
            elif isinstance(value,list):
                for child in value:
                    walk(child)
        walk(api)

    def test_migrations_are_host_neutral_and_no_http_triggers(self):
        for file in (ROOT/"db/migrations").glob("*.sql"):
            text = file.read_text().lower()
            for forbidden in ("auth.uid", "supabase", "http_post", "net.http", "vault.", "pg_cron"):
                self.assertNotIn(forbidden,text)
