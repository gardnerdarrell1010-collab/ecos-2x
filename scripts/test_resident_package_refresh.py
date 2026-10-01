"""A changed package releases ownership without executing or failing business work."""
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from runtime.resident2x.executor import Resident, WorkPackageChanged, OperationRejected


class PackageRefreshTest(unittest.TestCase):
    def test_forbidden_renewal_keeps_heartbeat_and_preserves_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            r = object.__new__(Resident)
            r.root = Path(folder)
            r.state_path = r.root / 'state.json'
            r.config = {'identity':'RESIDENT_ADA_2X_HOME01', 'instance_id':'fixture', 'authority':'fixture'}
            r.session = 'fixture'
            r.evidence_hash = '0' * 64
            r.client = Mock()
            r.stopping = Mock()
            r.stopping.is_set.return_value = False
            active = {'data':{'work_package':{'fence':{'claim_id':'fixture'}}}}
            r.state = {'cycle':7,'active':active}
            r.refresh_bootstrap = Mock()
            r.invoke = Mock(return_value={'data':{'authority':'fixture'}})
            r.heartbeat = Mock()
            r.execute = Mock(side_effect=OperationRejected('work.renew','forbidden'))
            r.finish_control = Mock()
            r._run_connected(max_cycles=2)
            self.assertEqual(r.heartbeat.call_count,3)
            self.assertEqual(r.state,{'cycle':7,'active':active})
            r.finish_control.assert_not_called()
            self.assertEqual(r.execute.call_count,2)
            self.assertIn('forbidden',(r.root/'failure.json').read_text())

    def test_dispatch_rejection_preserves_request_and_heartbeat(self):
        with tempfile.TemporaryDirectory() as folder:
            r = object.__new__(Resident)
            r.root = Path(folder)
            r.state_path = r.root / 'state.json'
            r.config = {'identity':'RESIDENT_ADA_2X_HOME01', 'instance_id':'fixture', 'authority':'fixture'}
            r.session = 'fixture'
            r.evidence_hash = '0' * 64
            r.client = Mock()
            r.stopping = Mock()
            r.stopping.is_set.return_value = False
            r.state = {'cycle':7,'active':None}
            r.refresh_bootstrap = Mock()
            r.invoke = Mock(side_effect=[{'data':{'authority':'fixture'}}, OperationRejected('work.next','gate_blocked')])
            r.heartbeat = Mock()
            r.execute = Mock()
            r._run_connected(max_cycles=1)
            self.assertEqual(r.heartbeat.call_count,2)
            self.assertEqual(r.state,{'cycle':7,'active':None})
            r.execute.assert_not_called()
            self.assertIn('gate_blocked',(r.root/'failure.json').read_text())

    def test_changed_package_releases_and_clears_local_claim(self):
        with tempfile.TemporaryDirectory() as folder:
            r = object.__new__(Resident)
            r.root = Path(folder)
            r.state_path = r.root / 'state.json'
            r.config = {'identity':'RESIDENT_ADA_2X_HOME01', 'instance_id':'fixture', 'authority':'fixture'}
            r.session = 'fixture'
            r.evidence_hash = '0' * 64
            r.client = Mock()
            r.stopping = threading.Event()
            fence = {'claim_id':'fixture'}
            r.state = {'cycle':0,'active':{'data':{'work_package':{'fence':fence}}}}
            r.refresh_bootstrap = Mock()
            r.invoke = Mock(return_value={'data':{'authority':'fixture'}})
            r.heartbeat = Mock()
            r.execute = Mock(side_effect=WorkPackageChanged('work_package_changed'))
            r.finish_control = Mock()
            r._run_connected(max_cycles=1)
            r.finish_control.assert_called_once_with('work.release',fence,'work_package_changed')
            self.assertIsNone(r.state['active'])
            self.assertEqual(r.state['cycle'],1)


if __name__ == '__main__':
    unittest.main()
