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

FAILED_RECEIPT_HASH='d22c9a449fc504884b1bc4a173f9fafbf4b917290efec417d15fc4fa9bcff7f5'
SAFE_KEYS={'rowData','sheets','data','values','pid','at','state','task_state','resident_pids',
           'slot','files','path','sha256','before_sha256','active_pointer_sha256','Value',
           'properties','title','sheetId','gridProperties','rowCount','principal_id','epoch',
           'generation','domain','target','database','password_file','sslmode','sslrootcert'}

def milestone(stage):
    """Failure injection seam; production performs no action here."""

def slot_changes(manifest):
    changed=[]
    for f in manifest['files']:
        target=SLOT/f['path']
        actual=digest(target.read_bytes()) if target.exists() else None
        if actual!=f['before_sha256']:changed.append(f['path'])
    return changed

def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--check-only',action='store_true')
    parser.add_argument('--attempt-id')
    args=parser.parse_args()
    attempt=str(uuid.UUID(args.attempt_id)) if args.attempt_id else str(uuid.uuid4())
    run_id='RUN-WAVE1-BOUNDARY-'+attempt
    receipt=HERE/'attempts'/(attempt+'.json')
    stop=NODE/'runtime/authoritative-command/ada-runtime/stop.requested'
    report={'at':now(),'AttemptID':attempt,'Administrator':bool(ctypes.windll.shell32.IsUserAnAdmin()),
            'Installed':False,'PostInstallVerified':False,'Resident1xHealthy':None,
            'Resident2xStillRunning':None,'MaintenanceRestored':False,'InstallationMutationOccurred':False,
            'AuthorityTransferred':False,'ReconciliationRequired':False,'Error':None,
            'ExceptionType':None,'FailureStage':None,'MissingKey':None}
    stage='initialization';own_receipt=False;acquired=False;maintenance_attempted=False
    stop_owned=False;restart_started=False;installation_started=False;run_created=False
    governance=None;manifest=None;release=None
    def enter(name):
        nonlocal stage
        stage=name;milestone(name)
    def persist():
        if own_receipt:save(receipt,report)
    try:
        if not args.check_only:
            require(args.attempt_id is not None,'attempt_identity_required')
            require(report['Administrator'],'administrator_required')
            receipt.parent.mkdir(exist_ok=True)
            with receipt.open('x',encoding='utf-8') as stream:stream.write(json.dumps(report,indent=2))
            own_receipt=True
        enter('receipt_verification')
        require(digest(REPORT.read_bytes())==FAILED_RECEIPT_HASH,'failed_receipt_changed')
        enter('package_verification');manifest,payload=check_package()
        enter('governed_preflight');governance=Governance()
        before=governance.exact('Settings','Setting Key','ECOS_TASK_LOOP_MAINTENANCE_MODE')[2]['Value']
        require(str(before).upper()=='FALSE','maintenance_already_active')
        report['MaintenanceBefore']='FALSE'
        report['Grants']=check_guard(governance,payload)
        enter('run_record_preparation');governance.prepare_run(run_id)
        enter('resident2x_preflight')
        installed2x=json.loads((REPO/'.local/wave1-live-installation.json').read_text())
        heartbeat2x=Path(installed2x['state'])/'heartbeat.json'
        def read2x(expected=None):
            current=json.loads(heartbeat2x.read_text())
            age=(datetime.now(timezone.utc)-datetime.fromisoformat(current['at'].replace('Z','+00:00'))).total_seconds()
            require(0<=age<60 and (expected is None or current['pid']==expected),'resident2x_heartbeat_changed_or_stale')
            report['Resident2xStillRunning']=True;report['Resident2xPID']=current['pid']
            report['Resident2xHeartbeat']=current['at'];return current
        before2x=read2x()
        if args.check_only:
            report['ReadOnlyPreflight']=True;print(json.dumps(report));return 0
        require(not stop.exists(),'foreign_stop_request')
        enter('resident1x_discovery')
        from ecos_runtime.resident_release import ResidentRelease
        release=ResidentRelease(NODE)
        state=release._drain_process_state()
        require(state['task_state']=='Running' and state['resident_pids'],'resident_not_running')
        hb=json.loads((NODE/'runtime/resident-ada/heartbeat.json').read_text())
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(hb['heartbeat_at'].replace('Z','+00:00'))).total_seconds()
        require(hb['pid'] in state['resident_pids'] and 0<=age<60,'resident1x_heartbeat_stale')
        report['Resident1xHealthy']=True;report['Resident1xPID']=hb['pid']
        enter('backup')
        backup=HERE/('backup-'+run_id);backup.mkdir()
        for f in manifest['files']:
            if f['before_sha256']:
                target=backup/f['path'];target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes((SLOT/f['path']).read_bytes())
                require(digest(target.read_bytes())==f['before_sha256'],'backup_hash')
        save(backup/'manifest.json',manifest)
        report['RunID']=run_id;report['Backup']=str(backup);persist()
        enter('run_record_creation');governance.create_run(run_id);run_created=True
        enter('maintenance_acquire')
        maintenance_attempted=True;governance.maintenance('TRUE','FALSE');acquired=True
        enter('stop_request')
        with stop.open('x',encoding='utf-8') as stream:stream.write(run_id)
        stop_owned=True;persist()
        enter('drain')
        deadline=time.monotonic()+120
        while not release.drain():
            require(time.monotonic()<deadline,'drain_not_verified');time.sleep(3)
        enter('preinstall_recheck');check_package();check_guard(governance,payload)
        enter('file_install');installation_started=True
        for f in manifest['files']:
            target=SLOT/f['path'];target.parent.mkdir(parents=True,exist_ok=True)
            temporary=target.with_name(target.name+'.'+run_id+'.tmp')
            temporary.write_bytes(payload[f['path']]);os.replace(temporary,target)
            enter('file_replaced')
            require(digest(target.read_bytes())==f['sha256'],'installed_hash')
        report['Installed']=True;report['InstallationMutationOccurred']=True;persist()
        enter('installed_import')
        verification="import sys;sys.path.insert(0,"+repr(str(SLOT))+");import psycopg;from ecos_runtime import domain_authority;assert psycopg.__version__=='3.2.10';assert psycopg.pq.__impl__=='binary'"
        subprocess.run([str(NODE/'runtime/python-envs/0.4.136-rc.1/python.exe'),'-I','-S','-B','-c',verification],check=True,capture_output=True,timeout=30)
        enter('restart');restart_started=True
        require(release.restart(SLOT),'restart_outcome_requires_reconciliation')
        enter('postinstall_verification')
        identity=release.runtime_identity();require(bool(identity),'runtime_identity')
        report['Resident1xHealthy']=True;report['Resident1xPID']=identity['pid'];report['RestartNonce']=release.nonce
        require(all(digest((SLOT/f['path']).read_bytes())==f['sha256'] for f in manifest['files']),'post_install_hash')
        require(digest((NODE/'runtime/releases/active.json').read_bytes())==manifest['active_pointer_sha256'],'post_install_pointer')
        check_guard(governance,payload);read2x(before2x['pid']);report['PostInstallVerified']=True
        enter('maintenance_release')
        require(stop.read_text(encoding='utf-8')==run_id,'stop_owner_changed')
        stop.unlink();stop_owned=False
        governance.maintenance('FALSE','TRUE');acquired=False;report['MaintenanceRestored']=True
        enter('run_completion')
        governance.update_run(run_id,{'Status':'Completed','Commit Verified':'TRUE','Lock Expires':'','Updated':now(),
            'Source Boundary End':json.dumps({'bundle_sha256':BUNDLE_HASH,'files':len(manifest['files']),
                'resident_pid':report['Resident1xPID'],'restart_nonce':release.nonce,'authority_transfer':False}),
            'Preflight Status':'Passed: installed hashes, existing scheduled-task restart, isolated identity and current 1X epoch 1 grants'})
        require(digest(REPORT.read_bytes())==FAILED_RECEIPT_HASH,'failed_receipt_changed')
    except Exception as error:
        import traceback
        report['ExceptionType']=type(error).__name__;report['Error']=type(error).__name__
        report['FailureStage']=stage
        if isinstance(error,KeyError):report['MissingKey']=error.args[0] if error.args and error.args[0] in SAFE_KEYS else '[redacted]'
        frames=[f for f in traceback.extract_tb(error.__traceback__) if Path(f.filename).resolve()==Path(__file__).resolve()]
        if frames:report['FailureFunction']=frames[-1].name;report['FailureLine']=frames[-1].lineno
        mutation_unknown=False
        try:
            changed=slot_changes(manifest) if installation_started else []
            if installation_started:
                changed.extend(f['path']+'.'+run_id+'.tmp' for f in manifest['files']
                    if (SLOT/f['path']).with_name(Path(f['path']).name+'.'+run_id+'.tmp').exists())
        except Exception:changed=[];mutation_unknown=True
        report['ChangedFiles']=changed
        report['InstallationMutationOccurred']=bool(changed) or mutation_unknown
        # No automatic rollback/restart after possible slot mutation. Preserve
        # the verified backup and owned maintenance for explicit reconciliation.
        safe_unmodified=not changed and not mutation_unknown and not restart_started
        safe_completed=report['PostInstallVerified'] and not mutation_unknown
        if acquired and (safe_unmodified or safe_completed):
            try:
                if safe_completed:
                    require(all(digest((SLOT/f['path']).read_bytes())==f['sha256'] for f in manifest['files']),'recovery_postimage_changed')
                    require(release.runtime_identity()['pid']==report['Resident1xPID'],'recovery_runtime_changed')
                else:require(not slot_changes(manifest),'recovery_preimage_changed')
                state=release._drain_process_state()
                require(state['task_state']=='Running' and state['resident_pids'],'recovery_requires_runtime_reconciliation')
                if stop_owned:
                    require(stop.read_text(encoding='utf-8')==run_id,'stop_owner_changed')
                    stop.unlink();stop_owned=False
                else:require(not stop.exists(),'foreign_stop_request')
                governance.maintenance('FALSE','TRUE');acquired=False
                report['MaintenanceRestored']=True
            except Exception as recovery_error:
                report['RecoveryExceptionType']=type(recovery_error).__name__
        if governance is not None:
            try:
                current=str(governance.exact('Settings','Setting Key','ECOS_TASK_LOOP_MAINTENANCE_MODE')[2]['Value']).upper()
                report['MaintenanceAfter']=current
                if current=='FALSE' and not acquired:report['MaintenanceRestored']=True
            except Exception:report['MaintenanceAfter']='UNKNOWN'
        report['MaintenanceMayRemainOwned']=acquired or (maintenance_attempted and report.get('MaintenanceAfter')!='FALSE')
        report['StopRequestOwned']=stop_owned;report['RestartStarted']=restart_started
        report['ReconciliationRequired']=bool(report['MaintenanceMayRemainOwned'] or changed or mutation_unknown or restart_started or stage in ('run_record_creation','run_completion'))
        if run_created and not report['ReconciliationRequired']:
            try:governance.update_run(run_id,{'Status':'Failed','Commit Verified':'FALSE','Lock Expires':'','Updated':now(),
                       'Preflight Status':'Installer failed closed at '+stage+'; slot unchanged; maintenance restored'})
            except Exception:report['ReconciliationRequired']=True
        persist();print(json.dumps(report));return 1
    persist();print(json.dumps(report));return 0

if __name__=='__main__':sys.exit(main())
