"""Bounded Administrator activation using the existing Resident release lifecycle.

No authority transfer, task Enabled changes, migrations, or 2.x work grants.
An ambiguous restart leaves maintenance owned and reports reconciliation required.
"""
import ctypes, hashlib, importlib.util, json, os, subprocess, sys, time, uuid, zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERE=Path(__file__).resolve().parent
NODE=Path('D:/ECOS/Node')
SLOT=NODE/'runtime/releases/slots/1.0.011'
REPO=Path('C:/ECOS/ecos-2x')
SID='1LF0isNKZBgEbr8E_pzekSWJ8-iXGfGn3e3xteKuivu0'
HEAD='a1d8eb9d2e7469b46148be6272a55befce576fc6'
BUNDLE_HASH='34b63539e21bfa075a92b26bdfdc38bb1ae2fddf3d5fbb40b93124824826fadc'
REPORT=HERE/'legacy-boundary-installation.json'
sys.dont_write_bytecode=True
sys.path.insert(0,str(SLOT))

def now():return datetime.now(timezone.utc).isoformat()
def digest(data):return hashlib.sha256(data).hexdigest()
def require(ok,code):
    if not ok:raise RuntimeError(code)
def save(path,value):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,indent=2),encoding='utf-8');os.replace(temp,path)
def cells(values):return [{'userEnteredValue':{'stringValue':str(v)}} for v in values]

class Governance:
    def __init__(self):
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        credential=service_account.Credentials.from_service_account_file(
            'D:/ECOS/Credentials/ecos-resident-ada.json',scopes=['https://www.googleapis.com/auth/spreadsheets'])
        self.service=build('sheets','v4',credentials=credential,cache_discovery=False,static_discovery=False)
        self.api=self.service.spreadsheets()
        metadata=self.api.get(spreadsheetId=SID,fields='spreadsheetId,properties(title),sheets(properties)').execute()
        require(metadata['spreadsheetId']==SID and metadata['properties']['title']=='ECOS Master Database','workbook_identity')
        self.meta={s['properties']['title']:s['properties'] for s in metadata['sheets']}
    def rows(self,title):
        limit=self.meta[title]['gridProperties']['rowCount']
        end={'Settings':'H','Run Control':'N'}[title]
        return self.api.values().get(spreadsheetId=SID,range=f"'{title}'!A1:{end}{limit}").execute().get('values',[])
    def exact(self,title,key,value):
        rows=self.rows(title);head=rows[0];col=head.index(key)
        found=[(i+1,dict(zip(head,r+['']*(len(head)-len(r))))) for i,r in enumerate(rows[1:],1) if len(r)>col and r[col]==value]
        require(len(found)==1,'record_identity_'+title.replace(' ','_'))
        return head,*found[0]
    def batch(self,requests):return self.api.batchUpdate(spreadsheetId=SID,body={'requests':requests}).execute()
    def maintenance(self,wanted,expected):
        head,row,before=self.exact('Settings','Setting Key','ECOS_TASK_LOOP_MAINTENANCE_MODE')
        require(str(before['Value']).upper()==expected,'maintenance_owner_changed')
        col=head.index('Value')
        self.batch([{'findReplace':{'range':{'sheetId':self.meta['Settings']['sheetId'],'startRowIndex':row-1,'endRowIndex':row,'startColumnIndex':col,'endColumnIndex':col+1},'find':expected,'replacement':wanted,'matchEntireCell':True,'matchCase':False,'searchByRegex':False}}])
        require(str(self.exact('Settings','Setting Key','ECOS_TASK_LOOP_MAINTENANCE_MODE')[2]['Value']).upper()==wanted,'maintenance_readback')
    def prepare_run(self,run_id):
        head=self.rows('Run Control')[0]
        record={h:'' for h in head}
        record.update({'Run ID':run_id,'Pipeline ID':'WAVE1-AUTHORITY-BOUNDARY-INSTALL',
            'Run Type':'Owner-authorized development and installation','Status':'In Progress',
            'Lock Owner':'CODEX_DEVELOPMENT','Lock Acquired':now(),
            'Lock Expires':(datetime.now(timezone.utc)+timedelta(minutes=15)).isoformat(),
            'Preflight Status':'Passed: exact source, current 1X epoch 1 grants, isolated imports and Administrator visibility',
            'Schema Version':'ECOS-2026-08-03-APPROVAL1',
            'Source Boundary Start':'Owner-authorized Wave 1 A029/A047 provider-effect guard only; source ZIP SHA256 '+BUNDLE_HASH,
            'Commit Verified':'FALSE','Updated':now()})
        native=self.api.get(spreadsheetId=SID,ranges=["'Run Control'!A2:N2"],fields='sheets(data(rowData(values(userEnteredFormat,dataValidation))))').execute()
        # Sheets omits rowData when every requested optional format/validation
        # field is unset. Required sheet/data containers remain mandatory.
        row_data=native['sheets'][0]['data'][0].get('rowData',[])
        exemplar=row_data[0].get('values',[]) if row_data else []
        values=[]
        for i,h in enumerate(head):
            cell=dict(exemplar[i]) if i<len(exemplar) else {}
            cell['userEnteredValue']={'stringValue':record[h]};values.append(cell)
        return record,values
    def create_run(self,run_id):
        record,values=self.prepare_run(run_id)
        self.batch([{'appendCells':{'sheetId':self.meta['Run Control']['sheetId'],'rows':[{'values':values}],
                                  'fields':'userEnteredValue,userEnteredFormat,dataValidation'}}])
        fresh=self.api.get(spreadsheetId=SID,fields='sheets(properties)').execute()
        self.meta={s['properties']['title']:s['properties'] for s in fresh['sheets']}
        require(self.exact('Run Control','Run ID',run_id)[2]==record,'run_creation_readback')
    def update_run(self,run_id,fields):
        head,row,_=self.exact('Run Control','Run ID',run_id)
        self.batch([{'updateCells':{'range':{'sheetId':self.meta['Run Control']['sheetId'],'startRowIndex':row-1,'endRowIndex':row,
             'startColumnIndex':head.index(key),'endColumnIndex':head.index(key)+1},
             'rows':[{'values':cells([value])}],'fields':'userEnteredValue'}} for key,value in fields.items()])
        actual=self.exact('Run Control','Run ID',run_id)[2]
        require(all(str(actual[key])==str(value) for key,value in fields.items()),'run_update_readback')

def check_package():
    require(digest((HERE/'wave1-authority-boundary-final.zip').read_bytes())==BUNDLE_HASH,'bundle_hash')
    with zipfile.ZipFile(HERE/'wave1-authority-boundary-final.zip') as archive:
        manifest=json.loads(archive.read('install-manifest.json'))
        require(len(archive.namelist())==len(set(archive.namelist())),'duplicate_archive_path')
        require(set(archive.namelist())=={'install-manifest.json'}|{f['path'] for f in manifest['files']},'archive_inventory')
        payload={f['path']:archive.read(f['path']) for f in manifest['files']}
    require(Path(manifest['slot'])==SLOT,'slot_identity')
    require(digest((NODE/'runtime/releases/active.json').read_bytes())==manifest['active_pointer_sha256'],'active_pointer_changed')
    for f in manifest['files']:
        target=SLOT/f['path']
        require(target.resolve().is_relative_to(SLOT.resolve()),'target_escapes_slot')
        require(digest(payload[f['path']])==f['sha256'],'payload_hash')
        require((digest(target.read_bytes()) if target.exists() else None)==f['before_sha256'],'installed_preimage_changed')
        if target.suffix=='.py':compile(payload[f['path']],f['path'],'exec')
        if not f['path'].startswith('ecos_runtime/'):
            require(digest((REPO/'.venv/Lib/site-packages'/f['path']).read_bytes())==f['sha256'],'installer_dependency_changed')
    git='C:/Program Files/Git/cmd/git.exe'
    require(subprocess.check_output([git,'-C',str(REPO),'rev-parse','HEAD'],text=True).strip()==HEAD,'head_changed')
    require(not subprocess.check_output([git,'-C',str(REPO),'status','--porcelain'],text=True).strip(),'repository_dirty')
    return manifest,payload

def check_guard(governance,payload):
    # Only the installer uses the existing venv dependency tree. The live 1.x
    # process continues to use -I -S and its own verified vendored release.
    dependency=str(REPO/'.venv/Lib/site-packages')
    if dependency not in sys.path:sys.path.append(dependency)
    from types import ModuleType,SimpleNamespace
    for name in ('domain_effects','domain_authority'):
        qualified='ecos_runtime.'+name
        module=ModuleType(qualified);module.__package__='ecos_runtime';sys.modules[qualified]=module
        exec(compile(payload['ecos_runtime/'+name+'.py'],name,'exec'),module.__dict__)
    dispatcher=SimpleNamespace(service=governance.service,spreadsheet_id=SID)
    grants=[]
    for task in ('TASK-AUTO-000029','TASK-AUTO-000047'):
        _,grant=sys.modules['ecos_runtime.domain_authority'].capture(dispatcher,SimpleNamespace(task_id=task))
        require(grant['generation']=='1X' and grant['epoch']==1 and grant['domain']=='toast.acquisition','authority_changed')
        grants.append(grant)
    return grants

PRIOR_RECEIPTS={
 'legacy-boundary-installation.json':'d22c9a449fc504884b1bc4a173f9fafbf4b917290efec417d15fc4fa9bcff7f5',
 'attempts/5e384cea-96c6-4a29-910f-2281d16b58b3.json':'fcf5448a0bd37060db83a004a6b9e2b347e81fafb6b12da7f0370e108fcbcf61'}

WINDOWS_TASK=r'''& { param($action,$launcher,$nodeRoot)
$ErrorActionPreference='Stop'
$lp='(?i)(?:^|[\s"''])'+[regex]::Escape($launcher)+'(?=$|[\s"''])'
$rp='(?i)(?:^|[\s"''])'+[regex]::Escape($nodeRoot)+'(?=$|[\s"''])'
$py='(?i)(?:^|[\s"''])'+[regex]::Escape((Join-Path $nodeRoot 'Start-EcosResidentAda.py'))+'(?=$|[\s"''])'
$tasks=@(Get-ScheduledTask | Where-Object { @($_.Actions | Where-Object { $_.Arguments -match $lp }).Count -gt 0 })
if($tasks.Count -ne 1){throw 'task_identity'}
$task=$tasks[0]
function ResidentProcesses {
 @(Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -and
   (($_.CommandLine -match $rp -and $_.CommandLine -match '(?i)(?:^|\s)node-resident(?:\s|$)') -or $_.CommandLine -match $py) })
}
if($action -eq 'stop') {
 $original=@(ResidentProcesses)
 Disable-ScheduledTask -InputObject $task | Out-Null
 Stop-ScheduledTask -InputObject $task
 for($i=0;$i -lt 3;$i++){if(!(ResidentProcesses).Count){break};Start-Sleep -Seconds 1}
 foreach($p in @(ResidentProcesses)) {
  $prior=@($original | Where-Object { $_.ProcessId -eq $p.ProcessId -and $_.CreationDate -eq $p.CreationDate -and $_.CommandLine -ceq $p.CommandLine })
  if($prior.Count -ne 1){throw 'process_identity_changed'}
  try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop }
  catch { if(Get-Process -Id $p.ProcessId -ErrorAction SilentlyContinue){throw} }
 }
 for($i=0;$i -lt 3;$i++){if(!(ResidentProcesses).Count){break};Start-Sleep -Seconds 1}
 if((ResidentProcesses).Count){throw 'resident_still_running'}
}
elseif($action -eq 'enable'){Enable-ScheduledTask -InputObject $task | Out-Null}
elseif($action -ne 'snapshot'){throw 'unsupported_action'}
$task=Get-ScheduledTask -TaskName $task.TaskName -TaskPath $task.TaskPath
$processes=@(ResidentProcesses | ForEach-Object { @{pid=[int]$_.ProcessId;parent_pid=[int]$_.ParentProcessId;created_at=$_.CreationDate.ToUniversalTime().ToString('o')} })
@{task_name=$task.TaskName;task_path=$task.TaskPath;task_state=[string]$task.State;enabled=[bool]$task.Settings.Enabled;
  processes=$processes;xml=(Export-ScheduledTask -TaskName $task.TaskName -TaskPath $task.TaskPath)} | ConvertTo-Json -Depth 5 -Compress
}'''

def preserved_receipts():
    for relative,expected in PRIOR_RECEIPTS.items():require(digest((HERE/relative).read_bytes())==expected,'prior_receipt_changed')

def private_directory(path):
    path.mkdir(parents=True,exist_ok=False)
    user=subprocess.check_output(['whoami'],text=True).strip()
    subprocess.run(['icacls',str(path),'/inheritance:r','/grant:r',user+':(OI)(CI)F',
                    '*S-1-5-18:(OI)(CI)F','*S-1-5-32-544:(OI)(CI)F'],check=True,capture_output=True)

def zero_effect_proven(row,snapshot,events):
    run=row['Current Run ID'];active=snapshot['host'].get('active_run') or {}
    phases=[e.get('phase') for e in events if e.get('run_id')==run]
    return (active.get('run_id')==run and active.get('task_id')==row['Task Loop ID']
        and snapshot['host'].get('last_phase') in ('CLAIM','VERIFY_OWNERSHIP')
        and bool(phases) and not any(p in {'EXECUTE','VERIFY','RECONCILE','RELEASE','CHECKPOINT'} for p in phases))

def failure_details(report,error,stage):
    import traceback
    report.update(ExceptionType=type(error).__name__,FailureStage=stage,MissingKey=None)
    safe={'rowData','sheets','data','values','pid','state','at','version','runtime_version','heartbeat_at',
          'dispatcher_id','task_state','enabled','processes','xml','slot','files','path','sha256','before_sha256'}
    if isinstance(error,KeyError):report['MissingKey']=error.args[0] if error.args and error.args[0] in safe else '[redacted]'
    frames=[f for f in traceback.extract_tb(error.__traceback__) if Path(f.filename).resolve()==Path(__file__).resolve()]
    if frames:report.update(FailureFunction=frames[-1].name,FailureLine=frames[-1].lineno)

def execute_install(ops,report):
    """Owner-authorized hard stop; no graceful drain call or readiness wait."""
    stage='capture_current_execution';stopping=False
    try:
        ops.capture_before()
        stage='enter_resident_maintenance';ops.enter_maintenance()
        stage='stop_resident_1x';stopping=True;ops.stop()
        stage='capture_stopped_execution';ops.capture_after()
        stage='protect_interrupted_execution';ops.protect_interrupted()
        stage='install';ops.install()
        stage='restart';ops.restart()
        stage='verify';ops.verify(True)
        report['Installed']=True;report['PostInstallVerified']=True
    except Exception as error:
        failure_details(report,error,stage);report.update(Installed=False,PostInstallVerified=False)
        # Stop only this Resident, restore exact preimages, then restore its
        # original startup path. Never treat an ambiguous candidate restart as
        # proof that it is safe to overwrite loaded files.
        if stopping:
            stopped=False;protected=False
            try:
                ops.stop();stopped=True
            except Exception as recovery_error:
                report['RecoveryExceptionType']=type(recovery_error).__name__
                report['ReconciliationRequired']=True
            if stopped:
                try:ops.capture_after();ops.protect_interrupted();protected=True
                except Exception as recovery_error:
                    report['RecoveryExceptionType']=type(recovery_error).__name__;report['ReconciliationRequired']=True
                # Restore files/startup even when an external evidence read is
                # unavailable; retain the local no-new-work marker in that case.
                try:ops.rollback();report['RollbackVerified']=True
                except Exception as recovery_error:
                    report['RecoveryExceptionType']=type(recovery_error).__name__;report['ReconciliationRequired']=True
            if report.get('RollbackVerified'):
                for retry in range(2):
                    try:
                        if retry:ops.stop()
                        ops.restart();ops.verify(False);report['RecoveredPriorRuntime']=True;break
                    except Exception as recovery_error:
                        report['RecoveryExceptionType']=type(recovery_error).__name__
                if not report.get('RecoveredPriorRuntime'):report['ReconciliationRequired']=True
        try:
            if not stopping or (report.get('RecoveredPriorRuntime') and protected):ops.restore_maintenance()
        except Exception as recovery_error:
            report['RecoveryExceptionType']=type(recovery_error).__name__;report['ReconciliationRequired']=True
        if report.get('RecoveredPriorRuntime'):
            try:ops.reconcile()
            except Exception as recovery_error:
                report['ReconciliationExceptionType']=type(recovery_error).__name__;report['ReconciliationRequired']=True
        return False
    try:
        ops.restore_maintenance()
        ops.reconcile()
    except Exception as error:
        report.update(ReconciliationRequired=True,ReconciliationExceptionType=type(error).__name__)
    return bool(report.get('MaintenanceRestored'))

class HardStopInstall:
    def __init__(self,attempt,report,manifest,payload,g):
        from ecos_runtime.resident_release import ResidentRelease
        self.attempt=attempt;self.report=report;self.manifest=manifest;self.payload=payload;self.g=g
        self.release=ResidentRelease(NODE);self.run_id='RUN-WAVE1-BOUNDARY-'+attempt
        self.stop_file=NODE/'runtime/authoritative-command/ada-runtime/stop.requested'
        self.private=NODE/'runtime/maintenance-evidence'/attempt
        private_directory(self.private)
        self.original={f['path']:(SLOT/f['path']).read_bytes() if f['before_sha256'] else None for f in manifest['files']}
        self.held={};self.snapshots=[];self.owns_stop=False;self.task_before=None;self.run_created=False
        proof=json.loads((REPO/'.local/wave1-live-installation.json').read_text())
        self.heartbeat2x=Path(proof['state'])/'heartbeat.json';self.pid2x=self.read2x()['pid']
    def windows(self,action):
        return json.loads(self.release._powershell(WINDOWS_TASK,action,str(NODE/'Start-EcosResidentAda.ps1'),str(NODE)))
    def read2x(self):
        hb=json.loads(self.heartbeat2x.read_text())
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(hb['at'].replace('Z','+00:00'))).total_seconds()
        require(0<=age<60,'resident2x_heartbeat_stale')
        if hasattr(self,'pid2x'):require(hb['pid']==self.pid2x,'resident2x_identity_changed')
        self.report.update(Resident2xHealthy=True,Resident2xPID=hb['pid']);return hb
    def tasks(self):
        from ecos_runtime.resident_governed import SheetsTable
        return SheetsTable(self.g.service,SID,'Task Loop')
    def capture(self,label):
        hb=json.loads((NODE/'runtime/resident-ada/heartbeat.json').read_text())
        host=json.loads((NODE/'runtime/authoritative-command/ada-runtime/state.json').read_text())
        dispatcher=host['dispatcher_id'];rows=self.tasks().records()
        claims=[r for r in rows if r.get('Claimed By')==dispatcher and (r.get('Claim Token') or r.get('Current Run ID'))]
        runs={r['Current Run ID'] for r in claims}
        records=self.g.rows('Run Control');head=records[0]
        reservations=[dict(zip(head,r)) for r in records[1:] if r and r[0] in runs]
        snapshot={'at':now(),'heartbeat':hb,'host':host,'claims':claims,'run_control':reservations}
        save(self.private/(label+'.json'),snapshot);self.snapshots.append(snapshot)
        return snapshot
    def capture_before(self):
        self.task_before=self.windows('snapshot')
        require(self.task_before['enabled'] and self.task_before['task_state']=='Running','resident1x_task_not_running')
        save(self.private/'task-before.json',self.task_before)
        snapshot=self.capture('before-stop')
        require(snapshot['heartbeat']['pid'] in [p['pid'] for p in self.task_before['processes']],'resident1x_pid_mismatch')
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(snapshot['heartbeat']['heartbeat_at'].replace('Z','+00:00'))).total_seconds()
        require(0<=age<60,'resident1x_heartbeat_stale')
        self.report.update(Resident1xHealthy=True,Resident1xPID=snapshot['heartbeat']['pid'],Resident1xVersion=snapshot['heartbeat']['runtime_version'])
        self.report['Resident1xPriorPID']=snapshot['heartbeat']['pid']
        self.report['MaintenanceBefore']=self.g.exact('Settings','Setting Key','ECOS_TASK_LOOP_MAINTENANCE_MODE')[2]['Value']
        require(str(self.report['MaintenanceBefore']).upper()=='FALSE','global_maintenance_already_active')
        for f in self.manifest['files']:
            if self.original[f['path']] is not None:
                dest=self.private/'backup'/f['path'];dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_bytes(self.original[f['path']]);require(digest(dest.read_bytes())==f['before_sha256'],'backup_hash')
        save(self.private/'manifest.json',self.manifest)
        self.g.create_run(self.run_id);self.run_created=True
    def enter_maintenance(self):
        # Existing Resident-only stop marker. Global Task Loop maintenance and
        # Online Ada are untouched. Task disabling below prevents auto-relaunch.
        with self.stop_file.open('x',encoding='utf-8') as stream:stream.write(self.run_id)
        self.owns_stop=True
    def stop(self):
        self.report.update(Resident1xHealthy=None,Resident1xPID=None)
        state=self.windows('stop')
        require(not state['processes'] and not state['enabled'],'resident1x_not_physically_stopped')
        self.report.update(Resident1xProcessStopped=True,Resident1xHealthy=False)
        self.read2x()
    def capture_after(self):
        require(not self.windows('snapshot')['processes'],'capture_requires_stopped_process')
        self.stopped=self.capture('after-stop-'+str(len(self.snapshots)))
        wanted={r['Current Run ID'] for r in self.stopped['claims']};events=[]
        for line in (NODE/'runtime/resident-ada/events.jsonl').open(encoding='utf-8'):
            row=json.loads(line)
            if row.get('run_id') in wanted:events.append(row)
        self.events=events;save(self.private/'interrupted-events.json',events)
    @staticmethod
    def claim_identity(row):
        return {k:row.get(k,'') for k in ('Task Loop ID','Claim Token','Claim Version','Current Run ID','Claimed By')}
    def enabled(self,row,wanted):
        table=self.tasks();identity=self.claim_identity(row);found=table.exact_record(identity)
        require(found is not None,'interrupted_claim_identity_changed')
        head=table.rows()[0];col=head.index('Enabled');number,before=found
        self.g.batch([{'updateCells':{'range':{'sheetId':table._sheet_id(),'startRowIndex':number-1,'endRowIndex':number,
            'startColumnIndex':col,'endColumnIndex':col+1},'rows':[{'values':[{'userEnteredValue':{'boolValue':wanted}}]}],
            'fields':'userEnteredValue'}}])
        require(table.exact_record({**identity,'Enabled':'TRUE' if wanted else 'FALSE'}) is not None,'interrupted_hold_readback')
    def protect_interrupted(self):
        for row in self.stopped['claims']:
            key=row['Task Loop ID']
            if key not in self.held:
                self.held[key]={'row':row,'zero_effect':zero_effect_proven(row,self.stopped,self.events),
                    'was_enabled':str(row.get('Enabled')).upper()=='TRUE'}
                save(self.private/'interrupted-holds.json',self.held)
            self.enabled(row,False)
        self.report['InterruptedOccurrence']='NONE' if not self.held else sorted(self.held)
        self.report['InterruptedWorkReconciliation']='NONE' if not self.held else 'PENDING'
    def install(self):
        require(not self.windows('snapshot')['processes'],'install_requires_stopped_process')
        check_package();check_guard(self.g,self.payload)
        for f in self.manifest['files']:
            target=SLOT/f['path'];target.parent.mkdir(parents=True,exist_ok=True)
            temporary=target.with_name(target.name+'.'+self.attempt+'.tmp')
            temporary.write_bytes(self.payload[f['path']]);os.replace(temporary,target)
            self.report['InstallationMutationOccurred']=True
            require(digest(target.read_bytes())==f['sha256'],'installed_hash')
    def rollback(self):
        require(not self.windows('snapshot')['processes'],'rollback_requires_stopped_process')
        for f in self.manifest['files']:
            target=SLOT/f['path'];actual=digest(target.read_bytes()) if target.exists() else None
            require(actual in (f['before_sha256'],f['sha256']),'rollback_unexpected_source')
            if f['before_sha256']:
                require(digest((self.private/'backup'/f['path']).read_bytes())==f['before_sha256'],'rollback_backup_changed')
        for f in self.manifest['files']:
            target=SLOT/f['path']
            if f['before_sha256']:
                temporary=target.with_name(target.name+'.rollback-'+self.attempt)
                temporary.write_bytes((self.private/'backup'/f['path']).read_bytes());os.replace(temporary,target)
            elif target.exists():target.unlink()
        require(all((digest((SLOT/f['path']).read_bytes()) if (SLOT/f['path']).exists() else None)==f['before_sha256'] for f in self.manifest['files']),'rollback_verification')
    def restart(self):
        self.windows('enable')
        require(self.release.restart(SLOT),'resident1x_restart_failed')
    def verify(self,candidate):
        identity=self.release.runtime_identity();require(bool(identity),'resident1x_identity_failed')
        deadline=time.monotonic()+20
        while True:
            hb=json.loads((NODE/'runtime/resident-ada/heartbeat.json').read_text())
            age=(datetime.now(timezone.utc)-datetime.fromisoformat(hb['heartbeat_at'].replace('Z','+00:00'))).total_seconds()
            if hb['pid']==identity['pid'] and 0<=age<30:break
            require(time.monotonic()<deadline,'resident1x_new_heartbeat_missing');time.sleep(1)
        for f in self.manifest['files']:
            actual=digest((SLOT/f['path']).read_bytes()) if (SLOT/f['path']).exists() else None
            require(actual==f['sha256' if candidate else 'before_sha256'],'runtime_source_hash')
        state=self.windows('snapshot')
        require(state['enabled'] and state['task_state']=='Running','resident1x_task_unhealthy')
        from xml.etree.ElementTree import canonicalize
        require(canonicalize(state['xml'],strip_text=True)==canonicalize(self.task_before['xml'],strip_text=True),'scheduled_task_configuration_changed')
        require(digest((NODE/'runtime/releases/active.json').read_bytes())==self.manifest['active_pointer_sha256'],'active_pointer_changed')
        self.report.update(Resident1xHealthy=True,Resident1xPID=identity['pid'],Resident1xVersion=identity['version'])
        self.report.update(GuardLoaded=bool(candidate),RuntimeDispatcherSHA256=digest((SLOT/'ecos_runtime/resident_governed.py').read_bytes()))
        self.read2x();check_guard(self.g,self.payload)
        self.report.update(Wave1Authority='1X',Wave1Epoch=1)
    def restore_maintenance(self):
        if self.owns_stop:
            require(self.stop_file.read_text(encoding='utf-8')==self.run_id,'stop_owner_changed')
            self.stop_file.unlink();self.owns_stop=False
        current=self.g.exact('Settings','Setting Key','ECOS_TASK_LOOP_MAINTENANCE_MODE')[2]['Value']
        require(str(current).upper()=='FALSE','global_maintenance_changed')
        self.report['MaintenanceRestored']=True
    def reconcile(self):
        if not self.held:self.report['InterruptedWorkReconciliation']='NONE';return
        statuses={};dispatcher=None
        for key,held in self.held.items():
            row=held['row'];fresh=self.tasks().exact_record(self.claim_identity(row))
            if fresh is None:
                statuses[key]='IDENTITY_CHANGED_REQUIRES_RECONCILIATION';continue
            if not held['zero_effect']:
                statuses[key]='HELD_PROVIDER_RECONCILIATION_REQUIRED';continue
            try:
                if dispatcher is None:
                    from ecos_runtime.node_entrypoints import load_node_config,build_invoker
                    profile=json.loads((NODE/'config/node.json').read_text(encoding='utf-8-sig'))
                    config=load_node_config(Path(profile['google_service_account']),SID,NODE/'config/effective-settings.json')
                    dispatcher=build_invoker(config).dispatcher_factory(config)
                from ecos_runtime.ada_runtime import WorkerClaim
                from types import SimpleNamespace
                item=SimpleNamespace(task_id=key,payload=fresh[1])
                claim=WorkerClaim(key,row['Claim Token'],int(row['Claim Version']));run=row['Current Run ID']
                reason='Owner-authorized Resident runtime stop; durable pre-EXECUTE state proves zero business effect'
                expiry=datetime.fromisoformat(fresh[1]['Claim Expires At'].replace('Z','+00:00'))
                if expiry<=datetime.now(timezone.utc):dispatcher.reconcile_expired_claim(item,claim,run,reason=reason)
                else:
                    dispatcher.results[run]=SimpleNamespace(status='failed',details={'error':reason})
                    dispatcher.release(item,claim,run,'failed')
                after=self.tasks().exact_record({'Task Loop ID':key})[1]
                require(not after.get('Claim Token') and not after.get('Current Run ID'),'recovery_release_unverified')
                if held['was_enabled']:self.enabled(after,True)
                statuses[key]='RECOVERED_ZERO_EFFECT_NORMAL_RETRY'
            except Exception:statuses[key]='HELD_RECOVERY_RECONCILIATION_REQUIRED'
        self.report['InterruptedWorkReconciliation']=statuses
        self.report['ReconciliationRequired']=any(v!='RECOVERED_ZERO_EFFECT_NORMAL_RETRY' for v in statuses.values())
        save(self.private/'reconciliation.json',statuses)

def main():
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--attempt-id');parser.add_argument('--check-only',action='store_true');args=parser.parse_args()
    report={'Installed':False,'PostInstallVerified':False,'Resident1xHealthy':None,'Resident2xHealthy':None,
            'MaintenanceRestored':False,'InstallationMutationOccurred':False,'AuthorityTransferred':False,
            'ReconciliationRequired':False,'ExceptionType':None,'FailureStage':None}
    receipt=None;owned=False;ops=None
    try:
        preserved_receipts();manifest,payload=check_package();g=Governance();check_guard(g,payload)
        g.prepare_run('READ-ONLY-PREPARATION')
        if args.check_only:print(json.dumps({'ReadOnlyPreflight':True,'Authority':'1X','Epoch':1,'PriorReceiptsPreserved':True}));return 0
        require(ctypes.windll.shell32.IsUserAnAdmin(),'administrator_required')
        attempt=str(uuid.UUID(args.attempt_id));report.update(AttemptID=attempt,at=now())
        receipt=HERE/'attempts'/(attempt+'.json');receipt.parent.mkdir(exist_ok=True)
        with receipt.open('x',encoding='utf-8') as stream:stream.write(json.dumps(report))
        owned=True
        ops=HardStopInstall(attempt,report,manifest,payload,g)
        success=execute_install(ops,report)
        preserved_receipts()
        check_guard(g,payload)
        report.update(Wave1Authority='1X',Wave1Epoch=1)
        if ops.run_created:
            g.update_run(ops.run_id,{'Status':'Completed' if success else 'Failed','Commit Verified':'TRUE' if success else 'FALSE',
                'Lock Expires':'','Updated':now(),'Preflight Status':'Owner-authorized hard stop; '+('guard verified' if success else 'installation failed; inspect receipt'),
                'Source Boundary End':json.dumps(report,separators=(',',':'))})
        save(receipt,report);print(json.dumps(report));return 0 if success else 1
    except Exception as error:
        failure_details(report,error,report.get('FailureStage') or 'preflight_or_evidence')
        report['ReconciliationRequired']=bool(ops)
        if owned:save(receipt,report)
        print(json.dumps(report));return 1

if __name__=='__main__':sys.exit(main())
