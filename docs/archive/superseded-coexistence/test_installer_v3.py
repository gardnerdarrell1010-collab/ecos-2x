import contextlib,importlib.util,io,json,tempfile,unittest,uuid,sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,Mock
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('installer_v2',HERE/'install_legacy_boundary_v3.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class Regression(unittest.TestCase):
    def prepare(self,response):
        g=object.__new__(m.Governance)
        headers=['Run ID','Pipeline ID','Run Type','Status','Lock Owner','Lock Acquired','Lock Expires','Preflight Status','Schema Version','Source Boundary Start','Source Boundary End','Commit Verified','Updated']
        g.rows=Mock(return_value=[headers]);g.api=Mock();g.api.get.return_value.execute.return_value=response
        return g.prepare_run('SYNTHETIC')
    def test_exact_missing_rowData_response(self):
        response={'sheets':[{'data':[{}]}]}
        with self.assertRaisesRegex(KeyError,'rowData'):response['sheets'][0]['data'][0]['rowData'][0]
        record,values=self.prepare(response)
        self.assertEqual(record['Run ID'],'SYNTHETIC')
        self.assertTrue(all(set(cell)=={'userEnteredValue'} for cell in values))
    def test_native_validation_preserved(self):
        validation={'condition':{'type':'BOOLEAN'}}
        _,values=self.prepare({'sheets':[{'data':[{'rowData':[{'values':[{'dataValidation':validation}]}]}]}]})
        self.assertEqual(values[0]['dataValidation'],validation)
    def test_required_containers_not_defaulted(self):
        with self.assertRaises(KeyError):self.prepare({'sheets':[{}]})

class Safety(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.node=self.root/'node';self.slot=self.node/'runtime/releases/slots/1.0.011';self.slot.mkdir(parents=True)
        self.repo=self.root/'repo';(self.repo/'.local').mkdir(parents=True)
        self.state=self.root/'2x';self.state.mkdir()
        (self.state/'heartbeat.json').write_text(json.dumps({'pid':222,'at':m.now()}))
        (self.repo/'.local/wave1-live-installation.json').write_text(json.dumps({'state':str(self.state)}))
        hb=self.node/'runtime/resident-ada/heartbeat.json';hb.parent.mkdir(parents=True);hb.write_text(json.dumps({'pid':111,'heartbeat_at':m.now()}))
        self.stop=self.node/'runtime/authoritative-command/ada-runtime/stop.requested';self.stop.parent.mkdir(parents=True)
        self.pointer=self.node/'runtime/releases/active.json';self.pointer.write_bytes(b'unchanged-pointer')
        self.failed=self.root/'legacy-boundary-installation.json';self.failed.write_bytes(b'original-failed-evidence')
        self.second=self.root/'second-failed.json';self.second.write_bytes(b'second-failed-evidence')
        (self.slot/'original.py').write_bytes(b'old')
        self.payload={'original.py':b'new','added.py':b'added'}
        self.manifest={'files':[{'path':'original.py','before_sha256':m.digest(b'old'),'sha256':m.digest(b'new')},
                                {'path':'added.py','before_sha256':None,'sha256':m.digest(b'added')}],
                       'active_pointer_sha256':m.digest(self.pointer.read_bytes())}
        self.gov=SimpleNamespace(value='FALSE',authority=('1X',1),runs={},prepare_run=Mock(return_value=({},[])))
        self.gov.exact=lambda *a:([],2,{'Value':self.gov.value})
        def maintenance(wanted,expected):
            assert self.gov.value==expected;self.gov.value=wanted
        self.gov.maintenance=maintenance
        self.gov.create_run=lambda run:self.gov.runs.update({run:'In Progress'})
        self.gov.update_run=lambda run,fields:self.gov.runs.update({run:fields['Status']})
        self.release=Mock(nonce='synthetic-nonce')
        self.release._drain_process_state.return_value={'task_state':'Running','resident_pids':[111]}
        self.release.drain.return_value=True;self.release.restart.return_value=True
        self.release.runtime_identity.return_value={'pid':111}
        self.patches=contextlib.ExitStack()
        for name,value in {'HERE':self.root,'NODE':self.node,'SLOT':self.slot,'REPO':self.repo,'REPORT':self.failed,
                           'FAILED_RECEIPT_HASH':m.digest(self.failed.read_bytes()),'SECOND_RECEIPT':self.second,
                           'SECOND_RECEIPT_HASH':m.digest(self.second.read_bytes())}.items():self.patches.enter_context(patch.object(m,name,value))
        self.patches.enter_context(patch.object(m,'check_package',return_value=(self.manifest,self.payload)))
        self.patches.enter_context(patch.object(m,'check_guard',side_effect=lambda *a:[{'domain':'toast.acquisition','generation':self.gov.authority[0],'epoch':self.gov.authority[1]}]))
        self.patches.enter_context(patch.object(m,'Governance',return_value=self.gov))
        self.patches.enter_context(patch.object(m.ctypes.windll.shell32,'IsUserAnAdmin',return_value=1))
        self.patches.enter_context(patch.object(m.subprocess,'run'))
        self.patches.enter_context(patch('ecos_runtime.resident_release.ResidentRelease',return_value=self.release))
    def tearDown(self):self.patches.close();self.tmp.cleanup()
    def run_attempt(self,stage=None,attempt=None):
        attempt=attempt or str(uuid.uuid4())
        def inject(actual):
            if actual==stage:raise KeyError('rowData')
        with patch.object(sys,'argv',['installer','--attempt-id',attempt]),patch.object(m,'milestone',side_effect=inject),contextlib.redirect_stdout(io.StringIO()) as out:
            code=m.main()
        result=json.loads(out.getvalue());self.assertEqual(self.failed.read_bytes(),b'original-failed-evidence')
        self.assertEqual(self.second.read_bytes(),b'second-failed-evidence')
        self.assertEqual(self.gov.authority,('1X',1));self.assertFalse(result['AuthorityTransferred'])
        self.assertEqual(json.loads((self.state/'heartbeat.json').read_text())['pid'],222)
        return code,result,attempt
    def check_stage(self,stage):
        code,r,_=self.run_attempt(stage)
        self.assertEqual(code,1);self.assertEqual(r['ExceptionType'],'KeyError');self.assertEqual(r['MissingKey'],'rowData')
        self.assertEqual(r['FailureStage'],stage)
        if stage in ('file_replaced','installed_import','restart','postinstall_verification'):
            self.assertTrue(r['InstallationMutationOccurred']);self.assertTrue(r['ReconciliationRequired'])
            self.assertEqual(self.gov.value,'TRUE');self.assertTrue(self.stop.exists())
            backups=list(self.root.glob('backup-*/original.py'));self.assertEqual(len(backups),1)
            self.assertEqual(backups[0].read_bytes(),b'old')
        else:
            self.assertEqual(self.gov.value,'FALSE');self.assertFalse(self.stop.exists())
        if not r['InstallationMutationOccurred']:self.assertEqual((self.slot/'original.py').read_bytes(),b'old')
    def test_success_preserves_old_receipt_and_both_identities(self):
        code,r,_=self.run_attempt();self.assertEqual(code,0);self.assertTrue(r['PostInstallVerified'])
        self.assertTrue(r['MaintenanceRestored']);self.assertEqual(r['Resident2xPID'],222)
    def test_retry_is_new_receipt_and_existing_attempt_refused(self):
        _,_,first=self.run_attempt('backup');original=(self.root/'attempts'/(first+'.json')).read_bytes()
        code,r,_=self.run_attempt(attempt=first);self.assertEqual(code,1);self.assertEqual(r['ExceptionType'],'FileExistsError')
        self.assertEqual((self.root/'attempts'/(first+'.json')).read_bytes(),original)
        _,_,second=self.run_attempt('backup');self.assertNotEqual(first,second)
    def test_temporary_write_is_detected(self):
        real_replace=m.os.replace
        def fail(source,dest):
            if Path(dest).parent==self.slot:raise KeyError('rowData')
            return real_replace(source,dest)
        with patch.object(m.os,'replace',side_effect=fail):code,r,_=self.run_attempt()
        self.assertEqual(code,1);self.assertTrue(r['InstallationMutationOccurred']);self.assertTrue(r['ReconciliationRequired'])
        self.assertEqual((self.slot/'original.py').read_bytes(),b'old')
    def test_unknown_key_redacted(self):
        with patch.object(m,'check_package',side_effect=KeyError('synthetic-secret-never-output')):
            _,r,_=self.run_attempt()
        self.assertEqual(r['MissingKey'],'[redacted]');self.assertNotIn('synthetic-secret-never-output',json.dumps(r))
    def test_ambiguous_maintenance_write_not_assumed_restored(self):
        def ambiguous(wanted,expected):
            self.gov.value=wanted;raise KeyError('rowData')
        self.gov.maintenance=ambiguous
        _,r,_=self.run_attempt()
        self.assertEqual(self.gov.value,'TRUE');self.assertTrue(r['ReconciliationRequired'])
        self.assertFalse(r['MaintenanceRestored']);self.assertFalse(r['InstallationMutationOccurred'])
    def test_foreign_stop_request_is_preserved(self):
        def fail_drain():
            self.stop.write_text('FOREIGN-OWNER');raise KeyError('rowData')
        self.release.drain.side_effect=fail_drain
        _,r,_=self.run_attempt()
        self.assertEqual(self.stop.read_text(),'FOREIGN-OWNER');self.assertTrue(r['ReconciliationRequired'])
        self.assertEqual(self.gov.value,'TRUE')
    def test_ambiguous_restart_keeps_verified_backup_and_maintenance(self):
        self.release.restart.side_effect=KeyError('rowData')
        _,r,_=self.run_attempt()
        self.assertTrue(r['RestartStarted']);self.assertTrue(r['ReconciliationRequired'])
        self.assertEqual(self.gov.value,'TRUE');self.assertTrue(self.stop.exists())
        self.assertEqual(next(self.root.glob('backup-*/original.py')).read_bytes(),b'old')

for stage in ('receipt_verification','package_verification','governed_preflight','run_record_preparation',
 'resident2x_preflight','resident1x_discovery','backup','run_record_creation','maintenance_acquire',
 'stop_request','drain','preinstall_recheck','file_install','file_replaced','installed_import','restart',
 'postinstall_verification','maintenance_release','run_completion'):
    setattr(Safety,'test_keyerror_'+stage,lambda self,stage=stage:self.check_stage(stage))

class DrainRegression(unittest.TestCase):
    def exercise(self,timeout,ready_after=171.690464,phase='COMMAND_RETURN',pid=111,age=0):
        from datetime import datetime,timezone,timedelta
        from ecos_runtime.resident_release import ResidentRelease
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);heartbeat=root/'runtime/resident-ada/heartbeat.json';heartbeat.parent.mkdir(parents=True)
            release=ResidentRelease(root);elapsed=[0.0];report={}
            def write_heartbeat():
                ready=elapsed[0]>=ready_after
                heartbeat.write_text(json.dumps({'pid':pid,'resident_state':'WAITING_TO_REINVOKE' if ready else 'INVOKING_RUN_TASK_LOOP',
                    'heartbeat_at':(datetime.now(timezone.utc)-timedelta(seconds=age)).isoformat(),
                    'current_execution':{'phase':phase if ready else 'SCORE','worker_id':None,'run_id':None}}))
            def sleep(seconds):elapsed[0]+=seconds;write_heartbeat()
            write_heartbeat()
            with patch.object(m,'NODE',root),patch.object(release,'_drain_process_state',return_value={'task_state':'Running','resident_pids':[111]}):
                try:m.wait_for_drain(release,report,root/'trace.json',timeout=timeout,clock=lambda:elapsed[0],sleep=sleep)
                except RuntimeError as error:return False,elapsed[0],report,str(error)
            return True,elapsed[0],report,None
    def test_exact_observed_scoring_delay_exceeds_old_deadline(self):
        accepted,elapsed,report,error=self.exercise(120)
        self.assertFalse(accepted);self.assertEqual(elapsed,120);self.assertEqual(error,'drain_not_verified')
        self.assertFalse(report['DrainLastObservation']['graceful_state'])
    def test_unchanged_contract_accepts_after_observed_scoring_pass(self):
        accepted,elapsed,report,_=self.exercise(600)
        self.assertTrue(accepted);self.assertGreater(elapsed,171.690464);self.assertLess(elapsed,180)
        self.assertEqual(report['DrainLastObservation']['task_state'],'Running')
    def test_healthy_heartbeat_never_extends_deadline(self):
        accepted,elapsed,report,_=self.exercise(600,ready_after=9999)
        self.assertFalse(accepted);self.assertEqual(elapsed,600)
    def test_active_execution_is_not_drain(self):
        self.assertFalse(self.exercise(12,ready_after=0,phase='EXECUTE')[0])
    def test_wrong_pid_is_not_drain(self):
        self.assertFalse(self.exercise(12,ready_after=0,pid=999)[0])
    def test_stale_heartbeat_is_not_drain(self):
        self.assertFalse(self.exercise(12,ready_after=0,age=120)[0])

if __name__=='__main__':unittest.main(verbosity=2)
