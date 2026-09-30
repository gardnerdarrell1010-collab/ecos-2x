"""Offline safety tests. Real SQL/process evidence is recorded separately."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from runtime.resident2x.executor import Resident, OperationRejected, singleton
from runtime.resident2x.connection import connection_factory
from runtime.resident2x.capabilities import make_handlers
from ecos.core.contracts import content_hash


class ResidentTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = {"authority": "PRE_CUTOVER_NON_AUTHORITATIVE", "provider_effects_enabled": False,
            "state_directory": self.directory.name, "instance_id": "instance", "principal_id": "principal",
            "correlation_id": "correlation", "identity": "RESIDENT_ADA_2X_HOME01", "control_plane": "POSTGRESQL",
            "work_sources": ["POSTGRESQL"], "capabilities": {"ecos.2x.execute": 1}}
        self.runtime = Resident(self.config, Mock(), {})
        self.runtime.client = Mock()
        self.runtime.client.operate.return_value = {"status": "committed"}

    def test_no_authority_switch(self):
        for field, value in (("provider_effects_enabled", True), ("authority", "PRODUCTION")):
            with self.assertRaises(ValueError):
                Resident({**self.config, field: value}, Mock(), {})

    def test_owner_credentials_rejected(self):
        with self.assertRaises(ValueError):
            connection_factory({**self.config, "database": {"user": "postgres", "sslmode": "require"}})

    def test_journal_keeps_identical_request_across_restart(self):
        self.runtime.invoke("fact.record", {"statement": "Hello World"}, key="effect")
        original = self.runtime.client.operate.call_args.args[1]
        restarted = Resident(self.config, Mock(), {})
        restarted.client = self.runtime.client
        restarted.invoke("fact.record", {"statement": "changed"}, key="effect")
        self.assertEqual(original, restarted.client.operate.call_args.args[1])
        self.assertEqual(original["arguments"]["statement"], "Hello World")

    def test_ambiguous_commit_preserves_request(self):
        self.runtime.client.operate.side_effect = ConnectionError("synthetic")
        with self.assertRaises(ConnectionError):
            self.runtime.invoke("fact.record", {"statement": "Hello World"}, key="effect")
        saved = list((Path(self.directory.name) / "requests").glob("*.json"))
        self.assertEqual(len(saved), 1)
        self.assertNotIn("result", json.loads(saved[0].read_text()))

    def test_error_response_never_becomes_success(self):
        self.runtime.client.operate.return_value = {"code": "expired_fence"}
        with self.assertRaises(OperationRejected):
            self.runtime.invoke("work.renew", {}, key="renew")

    def test_singleton_is_exclusive_and_released(self):
        path = Path(self.directory.name) / "resident2x.lock"
        with singleton(path):
            with self.assertRaises(OSError):
                with singleton(path):
                    self.fail("duplicate resident")
        with singleton(path):
            pass

    def test_wrong_instance_cannot_reuse_state(self):
        (Path(self.directory.name) / "state.json").write_text(json.dumps({"instance_id": "other"}))
        with self.assertRaises(ValueError):
            Resident(self.config, Mock(), {})

    def test_readback_is_separate_connection_and_hash_checked(self):
        record = {"id": "id", "record_version": 1, "statement": "Hello World"}
        db = Mock()
        manager = Mock()
        manager.__enter__ = Mock(return_value=db)
        manager.__exit__ = Mock(return_value=False)
        self.runtime.connect = Mock(return_value=manager)
        db.execute.return_value.fetchone.return_value = ({"record": record, "content_hash": content_hash(record)},)
        self.assertEqual(self.runtime.read("fact", "id")["record"], record)
        self.runtime.connect.assert_called_once()
        db.execute.return_value.fetchone.return_value[0]["content_hash"] = "0" * 64
        with self.assertRaises(ValueError):
            self.runtime.read("fact", "id")

    def test_terminal_dispositions_keep_fence_and_intent(self):
        fence = {"claim_id": "claim", "claim_version": 7, "fence_token": "fence"}
        for action in ("work.fail", "work.defer", "work.release"):
            self.runtime.finish_control(action, fence, "synthetic_reason", until="2026-10-01T00:00:00Z", retryable=True)
            sent = self.runtime.client.operate.call_args.args[1]["arguments"]
            self.assertEqual(sent["fence"], fence)
            self.assertEqual("until" in sent, action == "work.defer")
            self.assertEqual("retryable" in sent, action == "work.fail")

    def test_capability_dispatch_has_no_provider_write_or_semantic(self):
        self.assertEqual(set(make_handlers(self.config)), {"hello_world", "artifact_read", "authenticated_http_read"})


if __name__ == "__main__":
    unittest.main()
