"""Connection loss must preserve ambiguous work and must not weaken fencing."""
import json
from pathlib import Path
from unittest.mock import Mock
import psycopg
import unittest
from tests.resident2x import test_resident
from runtime.resident2x.executor import OperationRejected


class ContinuityTests(unittest.TestCase):
    setUp = test_resident.ResidentTests.setUp
    def test_reconnect_preserves_active_claim_and_cycle(self):
        active = {"synthetic": "pending"}
        self.runtime.state.update(active=active, cycle=12)
        self.runtime._run_connected = Mock(side_effect=[psycopg.OperationalError(), None])
        self.runtime.stopping = Mock()
        self.runtime.stopping.is_set.return_value = False
        self.runtime.run(1)
        self.assertEqual(self.runtime.state['active'], active)
        self.assertEqual(self.runtime.state['cycle'], 12)
        self.runtime.stopping.wait.assert_called_once_with(2)
        self.assertEqual(self.runtime._run_connected.call_count, 2)

    def test_governance_rejection_never_retried(self):
        self.runtime._run_connected = Mock(side_effect=OperationRejected('executor.register','forbidden'))
        with self.assertRaises(OperationRejected):
            self.runtime.run(1)
        self.runtime._run_connected.assert_called_once()

    def test_shutdown_during_outage_preserves_state(self):
        self.runtime._run_connected = Mock(side_effect=psycopg.OperationalError())
        self.runtime.stopping = Mock()
        self.runtime.stopping.is_set.side_effect = [False, True]
        self.runtime.run(1)
        self.runtime._run_connected.assert_called_once()
        receipt=json.loads((Path(self.directory.name)/'connectivity.json').read_text())
        self.assertEqual(receipt['status'], 'reconnecting')

    def test_ambiguous_execution_is_not_marked_failed(self):
        self.runtime.state['active'] = {'data': {'work_package': {'fence': {}}}}
        self.runtime.client.operate.return_value = {'data': {'authority': self.config['authority']}}
        self.runtime.heartbeat = Mock()
        self.runtime.execute = Mock(side_effect=psycopg.OperationalError())
        self.runtime.finish_control = Mock()
        with self.assertRaises(psycopg.OperationalError):
            self.runtime._run_connected(1)
        self.runtime.finish_control.assert_not_called()
        self.assertIsNotNone(self.runtime.state['active'])
