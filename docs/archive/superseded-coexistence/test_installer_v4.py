import ast,importlib.util,json,subprocess,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('hardstop',HERE/'install_legacy_boundary_v4.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class FakeOps:
    def __init__(self,report,active=False,zero=False,fail=None,restart_failures=0):
        self.report=report;self.active=active;self.zero=zero;self.fail=fail;self.restart_failures=restart_failures
        self.running=True;self.resident2=True;self.maintenance=False;self.source=b'original';self.authority=('1X',1)
        self.calls=[];self.claim={'token':'synthetic-token','version':8,'run':'synthetic-run','lease':'synthetic-lease'} if active else None
        self.original_claim=dict(self.claim) if active else None;self.backup=None;self.held=False
    def step(self,name):
        self.calls.append(name)
        if self.fail==name:self.fail=None;raise RuntimeError('synthetic_failure')
    def capture_before(self):self.step('capture_before');self.backup=self.source
    def enter_maintenance(self):self.step('enter');self.maintenance=True
    def stop(self):self.step('stop');self.running=False;self.report['Resident1xHealthy']=False
    def capture_after(self):self.step('capture_after');assert not self.running
    def protect_interrupted(self):self.step('protect');self.held=self.active
    def install(self):
        assert not self.running;self.source=b'candidate';self.step('install')
    def rollback(self):assert not self.running;self.step('rollback');self.source=self.backup
    def restart(self):
        self.calls.append('restart')
        if self.restart_failures:self.restart_failures-=1;raise RuntimeError('synthetic_restart_failure')
        self.running=True
    def verify(self,candidate):
        self.step('verify');assert self.running and self.resident2
        assert self.source==(b'candidate' if candidate else b'original')
        self.report.update(Resident1xHealthy=True,Resident2xHealthy=True,Wave1Authority='1X',Wave1Epoch=1)
    def restore_maintenance(self):self.step('restore');self.maintenance=False;self.report['MaintenanceRestored']=True
    def reconcile(self):
        self.step('reconcile')
        if not self.active:self.report['InterruptedWorkReconciliation']='NONE'
        elif self.zero:
            self.claim=None;self.held=False;self.report['InterruptedWorkReconciliation']='RECOVERED_ZERO_EFFECT_NORMAL_RETRY'
        else:
            assert self.claim==self.original_claim;self.report.update(InterruptedWorkReconciliation='HELD_PROVIDER_RECONCILIATION_REQUIRED',ReconciliationRequired=True)

class TransactionTests(unittest.TestCase):
    def run_case(self,**kwargs):
        report={'AuthorityTransferred':False,'ReconciliationRequired':False};ops=FakeOps(report,**kwargs)
        result=m.execute_install(ops,report)
        self.assertTrue(ops.resident2);self.assertEqual(ops.authority,('1X',1));self.assertFalse(report['AuthorityTransferred'])
        return result,ops,report
    def test_no_active_worker_success(self):
        success,o,r=self.run_case();self.assertTrue(success);self.assertTrue(o.running);self.assertFalse(o.maintenance)
        self.assertEqual(o.calls,['capture_before','enter','stop','capture_after','protect','install','restart','verify','restore','reconcile'])
        self.assertEqual(r['InterruptedWorkReconciliation'],'NONE')
    def test_active_claim_preserved_when_provider_effect_unknown(self):
        success,o,r=self.run_case(active=True);self.assertTrue(success);self.assertTrue(o.running);self.assertTrue(o.held)
        self.assertEqual(o.claim,o.original_claim);self.assertTrue(r['ReconciliationRequired'])
    def test_zero_effect_existing_recovery_path(self):
        success,o,r=self.run_case(active=True,zero=True);self.assertTrue(success);self.assertIsNone(o.claim);self.assertFalse(o.held)
    def test_install_failure_rolls_back_and_restarts(self):
        success,o,r=self.run_case(fail='install');self.assertFalse(success);self.assertEqual(o.source,b'original')
        self.assertTrue(o.running);self.assertFalse(o.maintenance);self.assertTrue(r['RollbackVerified'])
    def test_candidate_restart_failure_rolls_back(self):
        success,o,r=self.run_case(restart_failures=1);self.assertFalse(success);self.assertTrue(o.running)
        self.assertEqual(o.source,b'original');self.assertTrue(r['RecoveredPriorRuntime'])
    def test_transient_prior_restart_failure_retries_only_after_verified_stop(self):
        success,o,r=self.run_case(restart_failures=2);self.assertFalse(success);self.assertTrue(o.running);self.assertTrue(r['RecoveredPriorRuntime'])
    def test_persistent_restart_failure_is_never_reported_healthy(self):
        success,o,r=self.run_case(restart_failures=9);self.assertFalse(success);self.assertFalse(o.running)
        self.assertTrue(o.maintenance);self.assertTrue(r['ReconciliationRequired']);self.assertFalse(r.get('RecoveredPriorRuntime',False))
        self.assertFalse(r['Resident1xHealthy'])
    def test_failure_with_claim_preserves_claim_and_restores_runtime(self):
        success,o,r=self.run_case(active=True,fail='install');self.assertFalse(success);self.assertTrue(o.running)
        self.assertEqual(o.claim,o.original_claim);self.assertTrue(o.held)
    def test_reconciliation_error_does_not_roll_back_healthy_install(self):
        success,o,r=self.run_case(active=True,fail='reconcile');self.assertTrue(success);self.assertTrue(o.running)
        self.assertEqual(o.source,b'candidate');self.assertTrue(r['ReconciliationRequired'])
    def test_installer_has_no_graceful_drain_calls(self):
        tree=ast.parse((HERE/'install_legacy_boundary_v4.py').read_text())
        self.assertFalse(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='drain' for n in ast.walk(tree)))

class EvidenceTests(unittest.TestCase):
    def test_failure_details_never_expose_unknown_key(self):
        report={};m.failure_details(report,KeyError('secret-value'),'capture');self.assertEqual(report['MissingKey'],'[redacted]')
        self.assertNotIn('secret-value',json.dumps(report))
        m.failure_details(report,KeyError('rowData'),'capture');self.assertEqual(report['MissingKey'],'rowData')
    def test_preexecute_proof(self):
        row={'Task Loop ID':'worker','Current Run ID':'run'};snap={'host':{'active_run':{'task_id':'worker','run_id':'run'},'last_phase':'VERIFY_OWNERSHIP'}}
        self.assertTrue(m.zero_effect_proven(row,snap,[{'run_id':'run','phase':'CLAIM'}]))
        self.assertFalse(m.zero_effect_proven(row,snap,[{'run_id':'run','phase':'EXECUTE'}]))
        self.assertFalse(m.zero_effect_proven(row,snap,[]))
    def test_real_rollback_restores_backup_and_removes_only_added_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);slot=root/'slot';slot.mkdir();private=root/'evidence';(private/'backup').mkdir(parents=True)
            (slot/'old.py').write_bytes(b'new');(slot/'added.py').write_bytes(b'added');(slot/'unrelated.py').write_bytes(b'untouched')
            (private/'backup/old.py').write_bytes(b'old')
            ops=object.__new__(m.HardStopInstall);ops.private=private;ops.attempt='test';ops.windows=Mock(return_value={'processes':[]})
            ops.manifest={'files':[{'path':'old.py','before_sha256':m.digest(b'old'),'sha256':m.digest(b'new')},
                                   {'path':'added.py','before_sha256':None,'sha256':m.digest(b'added')}]}
            with patch.object(m,'SLOT',slot):ops.rollback()
            self.assertEqual((slot/'old.py').read_bytes(),b'old');self.assertFalse((slot/'added.py').exists())
            self.assertEqual((slot/'unrelated.py').read_bytes(),b'untouched')
    def test_prior_receipts_verified_without_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'first').write_bytes(b'one');(root/'second').write_bytes(b'two')
            with patch.object(m,'HERE',root),patch.object(m,'PRIOR_RECEIPTS',{'first':m.digest(b'one'),'second':m.digest(b'two')}):m.preserved_receipts()
            self.assertEqual((root/'first').read_bytes(),b'one');self.assertEqual((root/'second').read_bytes(),b'two')
    def check_real_reconciliation(self,expired=False,ambiguous=False):
        from datetime import datetime,timezone,timedelta
        from types import SimpleNamespace
        row={'Task Loop ID':'synthetic-worker','Claim Token':'synthetic-token','Claim Version':'8','Current Run ID':'synthetic-run',
             'Claimed By':'synthetic-resident','Claim Expires At':(datetime.now(timezone.utc)+timedelta(hours=-1 if expired else 1)).isoformat(),'Enabled':'FALSE'}
        with tempfile.TemporaryDirectory() as directory:
            ops=object.__new__(m.HardStopInstall);ops.private=Path(directory);ops.report={}
            ops.held={'synthetic-worker':{'row':dict(row),'was_enabled':True,'zero_effect':not ambiguous}}
            table=Mock();table.exact_record.side_effect=lambda identity:(2,dict(row))
            ops.tasks=Mock(return_value=table)
            ops.enabled=Mock(side_effect=lambda r,wanted:row.update(Enabled='TRUE' if wanted else 'FALSE'))
            dispatcher=SimpleNamespace(results={})
            def clear(*a,**kw):row.update({'Claim Token':'','Current Run ID':''})
            dispatcher.release=Mock(side_effect=clear);dispatcher.reconcile_expired_claim=Mock(side_effect=clear)
            (Path(directory)/'config').mkdir();(Path(directory)/'config/node.json').write_text(json.dumps({'google_service_account':'synthetic'}))
            from ecos_runtime import node_entrypoints
            with patch.object(m,'NODE',Path(directory)),patch.object(node_entrypoints,'load_node_config',return_value=object()),patch.object(node_entrypoints,'build_invoker',return_value=SimpleNamespace(dispatcher_factory=lambda _:dispatcher)):
                ops.reconcile()
            if ambiguous:
                self.assertEqual(row['Claim Token'],'synthetic-token');self.assertEqual(row['Enabled'],'FALSE')
                dispatcher.release.assert_not_called();dispatcher.reconcile_expired_claim.assert_not_called()
                self.assertTrue(ops.report['ReconciliationRequired'])
            else:
                self.assertEqual(row['Claim Token'],'');self.assertEqual(row['Enabled'],'TRUE')
                (dispatcher.reconcile_expired_claim if expired else dispatcher.release).assert_called_once()
                self.assertFalse(ops.report['ReconciliationRequired'])
    def test_real_live_claim_recovery_routes_existing_release(self):self.check_real_reconciliation()
    def test_real_expired_claim_recovery_routes_existing_reconciliation(self):self.check_real_reconciliation(expired=True)
    def test_real_ambiguous_claim_is_not_replayed(self):self.check_real_reconciliation(ambiguous=True)

class WindowsStopTests(unittest.TestCase):
    def run_mock(self,normal):
        # These functions shadow every Windows operation. No real task/process
        # cmdlet is invoked; the production stop script itself is exercised.
        mock=r'''
$global:NormalStop=NORMAL
$global:Killed=@()
$global:T=[pscustomobject]@{TaskName='Resident';TaskPath='\';State='Running';Settings=[pscustomobject]@{Enabled=$true};Actions=@([pscustomobject]@{Arguments='-File D:\ECOS\Node\Start-EcosResidentAda.ps1 -Root D:\ECOS\Node'})}
$global:P=@(
 [pscustomobject]@{Name='python.exe';ProcessId=101;ParentProcessId=1;CreationDate=[DateTime]::UtcNow;CommandLine='python D:\ECOS\Node\Start-EcosResidentAda.py --root D:\ECOS\Node'},
 [pscustomobject]@{Name='python.exe';ProcessId=202;ParentProcessId=2;CreationDate=[DateTime]::UtcNow;CommandLine='python D:\ECOS\Node\runtime\resident2x\scripts\resident2x.py'},
 [pscustomobject]@{Name='python.exe';ProcessId=303;ParentProcessId=3;CreationDate=[DateTime]::UtcNow;CommandLine='python online-ada.py'})
function Get-ScheduledTask {param($TaskName,$TaskPath) $global:T}
function Get-CimInstance {param($ClassName) $global:P}
function Disable-ScheduledTask {param($InputObject) $global:T.Settings.Enabled=$false}
function Enable-ScheduledTask {param($InputObject) $global:T.Settings.Enabled=$true}
function Stop-ScheduledTask {param($InputObject) $global:T.State='Disabled';if($global:NormalStop){$global:P=@($global:P|Where-Object ProcessId -ne 101)}}
function Stop-Process {param($Id,[switch]$Force,$ErrorAction) $global:Killed+= $Id;$global:P=@($global:P|Where-Object ProcessId -ne $Id)}
function Get-Process {param($Id,$ErrorAction) $global:P|Where-Object ProcessId -eq $Id}
function Start-Sleep {param($Seconds)}
function Export-ScheduledTask {param($TaskName,$TaskPath) '<Task/>'}
'''.replace('NORMAL','$true' if normal else '$false')
        script=mock+'\n'+m.WINDOWS_TASK+r" 'stop' 'D:\ECOS\Node\Start-EcosResidentAda.ps1' 'D:\ECOS\Node'"
        script+="\nif (@($global:P).Count -ne 2 -or @($global:P|Where-Object ProcessId -eq 202).Count -ne 1 -or @($global:P|Where-Object ProcessId -eq 303).Count -ne 1){throw 'unrelated_process_changed'}"
        script+="\nif (@($global:Killed|Where-Object {$_ -ne 101}).Count){throw 'wrong_process_killed'}"
        result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(result.returncode,0,result.stderr)
        evidence=json.loads(result.stdout);self.assertFalse(evidence['processes']);self.assertFalse(evidence['enabled'])
    def test_normal_stop_touches_only_resident1x(self):self.run_mock(True)
    def test_forced_fallback_touches_only_resident1x(self):self.run_mock(False)

if __name__=='__main__':unittest.main(verbosity=2)
