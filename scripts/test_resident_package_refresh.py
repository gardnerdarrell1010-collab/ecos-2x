"""A changed package releases ownership without executing or failing business work."""
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from runtime.resident2x.executor import Resident, WorkPackageChanged


class PackageRefreshTest(unittest.TestCase):
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
