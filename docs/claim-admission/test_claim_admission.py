"""Exercise the actual candidate claim method with synthetic Sheets only."""
import concurrent.futures
import importlib.util
import json
import sys
import tempfile
import threading
import unittest
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
SLOT = Path(r'D:\ECOS\Node\runtime\releases\slots\1.0.011')
sys.dont_write_bytecode = True
sys.path.insert(0, str(SLOT))
spec = importlib.util.spec_from_file_location('ecos_runtime.claim_repair_candidate', HERE / 'resident_governed.py')
candidate = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = candidate
spec.loader.exec_module(candidate)
from ecos_runtime.task_loop_claimability import REQUIRED_FIELDS, fresh_execution_decision

RUN = ['Run ID','Pipeline ID','Run Type','Status','Lock Owner','Lock Acquired','Lock Expires','Preflight Status','Schema Version','Source Boundary Start','Source Boundary End','Commit Verified','Last Error','Updated']
CLAIM = ['Execution Status','Claimed By','Claim Token','Claim Version','Claimed At','Claim Expires At','Last Heartbeat At','Current Run ID']

class Fixture:
    def __init__(self, root):
        self.row = {field:'synthetic' for field in REQUIRED_FIELDS}
        self.row.update({'Task Loop ID':'SYNTHETIC-CLAIM-ADMISSION','Enabled':'TRUE',
            'Execution Mode':'Autonomous','Claim Version':'1','Claim Token':'','Claimed By':'',
            'Current Run ID':'','Occurrence ID':'synthetic-occurrence','Effective Ready At':''})
        self.selected = SimpleNamespace(task_id=self.row['Task Loop ID'], payload=dict(self.row))
        self.maintenance = 'FALSE'
        self.capability = True
        self.reservations = []
        self.writes = []
        self.on_append = lambda: None
        self.after_capability = lambda: None
        self.before_write = lambda: None
        self.settings_missing = False
        outer = self
        class RunTable:
            def records(self): return [dict(row) for row in outer.reservations]
            def append(self, values):
                outer.reservations.append(dict(zip(RUN,values)))
                outer.on_append()
                return 'APPEND_CELLS'
            def exact_record(self, expected):
                rows = [r for r in outer.reservations if all(r.get(k)==v for k,v in expected.items())]
                return (2,dict(rows[0])) if len(rows)==1 else None
        class TaskTable:
            def update_row(self, index, values, start, end):
                assert (index,start,end)==(2,'T','AA')
                outer.before_write()
                updates = {key:str(value) for key,value in zip(CLAIM,values)}
                outer.row.update(updates)
                outer.writes.append(updates)
        class Settings:
            def __init__(self,*args): pass
            def exact_record(self, expected):
                assert expected == {'Setting Key':'ECOS_TASK_LOOP_MAINTENANCE_MODE','Active':'TRUE'}
                return None if outer.settings_missing else (2,{'Value':outer.maintenance})
        self.settings_class = Settings
        self.dispatcher = candidate.ResidentGovernedDispatcher.__new__(candidate.ResidentGovernedDispatcher)
        self.dispatcher.__dict__.update(node_root=Path(root),claim_lease=timedelta(seconds=120),
            run=RunTable(),task=TaskTable(),reservations={},service=None,spreadsheet_id='synthetic',
            registry=SimpleNamespace(resolve=lambda *args: True),capabilities=set(),claimability={},
            ai_execution_throttle=None,_find=lambda _: (2,dict(self.row)))
        def capability(*args):
            self.after_capability()
            return {'executable': self.capability, 'reason':'synthetic capability mismatch'}
        self.dispatcher.executor_local_admission = capability

    def claim(self, owner='synthetic-owner', run='synthetic-run'):
        return self.dispatcher.claim(self.selected, owner, run)

class ClaimTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ecos-claim-test-')
        self.f = Fixture(self.temp.name)
        self.settings = patch.object(candidate,'SheetsTable',self.f.settings_class)
        self.sleeps = patch.object(candidate.time,'sleep',lambda _:None)
        self.settings.start(); self.sleeps.start()
    def tearDown(self):
        self.sleeps.stop(); self.settings.stop(); self.temp.cleanup()
    def assert_no_claim(self):
        self.assertIsNone(self.f.claim())
        self.assertEqual(self.f.writes, [])
        self.assertNotIn('Attempt Count', self.f.row)
        self.assertNotIn('Retry After', self.f.row)
    def test_selected_then_disabled(self):
        self.assertTrue(fresh_execution_decision(self.f.selected.payload).ready)
        self.f.row['Enabled']='FALSE'
        self.assert_no_claim()
        self.assertEqual(self.f.reservations, [])
    def test_still_enabled(self):
        self.assertIsNotNone(self.f.claim())
        self.assertEqual(len(self.f.writes),1)
    def test_existing_owner_survives_disable(self):
        claim=self.f.claim()
        self.f.row['Enabled']='FALSE'
        self.assertEqual(self.f.claim(),claim)
        self.assertIsNone(self.f.claim('other','other-run'))
        self.assertEqual(len(self.f.writes),1)
        self.assertIsNotNone(self.f.dispatcher._owned(self.f.selected,claim,'synthetic-run'))
        self.assertTrue(self.f.dispatcher._validate_delegated_claim(
            task_loop_id=self.f.selected.task_id,occurrence_id='synthetic-occurrence',
            run_id='synthetic-run',claimed_by='synthetic-owner',
            claim_token=claim.token,claim_version=claim.version)['verified'])
    def test_disabled_before_selection(self):
        self.f.row['Enabled']='FALSE'
        self.assertFalse(fresh_execution_decision(self.f.row).ready)
        self.assert_no_claim()
    def test_reenabled_before_boundary(self):
        self.f.row['Enabled']='FALSE'
        self.f.selected.payload['Enabled']='FALSE'
        self.f.row['Enabled']='TRUE'
        self.assertIsNotNone(self.f.claim())
    def test_version_changes_during_reservation(self):
        self.f.on_append=lambda: self.f.row.update({'Claim Version':'2'})
        self.assert_no_claim()
    def test_maintenance(self):
        self.f.maintenance='TRUE'
        self.assert_no_claim()
    def test_maintenance_during_reservation(self):
        self.f.on_append=lambda: setattr(self.f,'maintenance','TRUE')
        self.assert_no_claim()
    def test_missing_maintenance_fails_closed(self):
        self.f.settings_missing=True
        self.assert_no_claim()
    def test_capability_mismatch(self):
        self.f.capability=False
        self.assert_no_claim()
    def test_capability_changed_during_reservation(self):
        self.f.on_append=lambda: setattr(self.f,'capability',False)
        self.assert_no_claim()
    def test_disabled_during_reservation(self):
        self.f.on_append=lambda: self.f.row.update({'Enabled':'FALSE'})
        self.assert_no_claim()
    def test_disabled_during_capability_read(self):
        self.f.after_capability=lambda: self.f.row.update({'Enabled':'FALSE'})
        self.assert_no_claim()
    def test_future_timing(self):
        self.f.row['Next Eligible At']='2999-01-01T00:00:00Z'
        self.assert_no_claim()
    def test_changed_execution_definition(self):
        self.f.row['Instructions']='different current instructions'
        self.assert_no_claim()
    def test_concurrent_contenders_around_disable(self):
        reserved=threading.Event(); disabled=threading.Event()
        def pause():
            reserved.set()
            self.assertTrue(disabled.wait(5))
        self.f.on_append=pause
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            first=pool.submit(self.f.claim,'first','first-run')
            self.assertTrue(reserved.wait(5))
            self.f.row['Enabled']='FALSE'
            others=[pool.submit(self.f.claim,f'owner-{i}',f'run-{i}') for i in range(7)]
            disabled.set()
            self.assertIsNone(first.result())
            self.assertTrue(all(f.result() is None for f in others))
        self.assertEqual(self.f.writes,[])

class CommitBoundaryCounterexample(unittest.TestCase):
    def test_disable_after_last_read_before_unconditional_write(self):
        # Separate Sheets read/update RPCs have no common lock with an external
        # disable writer. This is intentionally a counterexample, not acceptance.
        with tempfile.TemporaryDirectory(prefix='ecos-commit-boundary-') as directory:
            f=Fixture(directory)
            f.before_write=lambda: f.row.update({'Enabled':'FALSE'})
            with patch.object(candidate,'SheetsTable',f.settings_class), patch.object(candidate.time,'sleep',lambda _:None):
                claim=f.claim()
            self.assertIsNotNone(claim)
            self.assertEqual(f.row['Enabled'],'FALSE')
            self.assertEqual(len(f.writes),1)
            (HERE/'commit-boundary-counterexample.json').write_text(json.dumps({
                'reproduced':True,'candidate_claimed_after_disable':True,
                'disable_timing':'after final authoritative read, before unconditional Sheets ownership update',
                'provider_calls':0,'production_writes':0,'live_runtime_probe':False,
                'transfer_safe':False},indent=2),encoding='utf-8')

if __name__ == '__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ClaimTests))
    (HERE/'focused-tests.json').write_text(json.dumps({'tests':result.testsRun,'failures':len(result.failures),
        'errors':len(result.errors),'passed':result.wasSuccessful(),'provider_calls':0,
        'live_runtime_probe':False},indent=2),encoding='utf-8')
    counterexample=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CommitBoundaryCounterexample))
    sys.exit(not (result.wasSuccessful() and counterexample.wasSuccessful()))
