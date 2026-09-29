import tempfile
import unittest
from pathlib import Path

from ecos.core.quarantine import classify_rows
from scripts.migrations import inventory, plan, render

ROOT = Path(__file__).resolve().parents[2]


class MigrationTests(unittest.TestCase):
    def test_framework_plan_repeat_drift_and_unknown_history(self):
        migrations = inventory(ROOT/"db/migrations")
        self.assertEqual(len(plan(migrations,[])),1)
        history = [{k:v for k,v in m.items() if k != "sql"} for m in migrations]
        self.assertEqual(plan(migrations,history),[])
        for bad in ([history[0] | {"sha256":"f"*64}], [history[0] | {"version":2}], history+[history[0]]):
            with self.assertRaises(ValueError):
                plan(migrations,bad)

    def test_migration_gaps_duplicate_versions_and_transaction_control_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root/"000002_gap.sql"
            file.write_text("select 1;",encoding="utf-8")
            with self.assertRaises(ValueError):
                inventory(root)
            file.unlink()
            file = root/"000001_test.sql"
            file.write_text("commit;",encoding="utf-8")
            with self.assertRaises(ValueError):
                inventory(root)
            file.write_text("select 1;",encoding="utf-8")
            (root/"000001_duplicate.sql").write_text("select 2;",encoding="utf-8")
            with self.assertRaises(ValueError):
                inventory(root)

    def test_render_is_transactional_and_contains_ledger_drift_guards(self):
        sql = render(inventory(ROOT/"db/migrations"))
        self.assertIn("pg_advisory_xact_lock",sql)
        self.assertIn("Migration drift",sql)
        self.assertIn("Non-contiguous migration history",sql)
        self.assertIn("ON_ERROR_STOP",sql)
        self.assertTrue(sql.endswith("commit;\n"))

    def test_duplicate_ids_preserve_each_source_locator(self):
        rows = [{"batch_id":"synthetic", "source_locator":str(n), "legacy_id":"duplicate",
                 "values":{"title":"test","version":1}} for n in (1,2)]
        classified = classify_rows(rows,["title","version"],{"title":str,"version":int})
        self.assertEqual(len(classified),2)
        self.assertTrue(all(r["state"]=="identity_unresolved" for r in classified))
        self.assertNotEqual(classified[0]["locator"],classified[1]["locator"])

    def test_column_drift_types_and_source_locator_collision(self):
        row = {"batch_id":"synthetic","source_locator":"1","legacy_id":"synthetic-1",
               "values":{"version":"narrative shifted", "title":42}}
        result = classify_rows([row],["title","version"],{"title":str,"version":int})[0]
        self.assertEqual(result["state"],"invalid")
        self.assertIn("column_drift",result["reason_codes"])
        self.assertIn("invalid_type.version",result["reason_codes"])
        with self.assertRaises(ValueError):
            classify_rows([row,row],["title","version"],{})
