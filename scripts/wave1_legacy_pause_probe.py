"""Zero-provider-effect reproduction using the installed 1.x claim methods.

All record reads and writes use in-memory synthetic doubles. A temporary local
claim lock is the only I/O performed by the imported methods.
"""
import hashlib,json,sys,tempfile
from pathlib import Path
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
SHARED=Path(r'D:\ECOS\Node\runtime\releases\slots\1.0.011')
sys.dont_write_bytecode=True;sys.path.insert(0,str(SHARED))
from ecos_runtime import resident_governed as legacy
from ecos_runtime.task_loop_claimability import fresh_execution_decision,REQUIRED_FIELDS

def probe():
    # A scan selected the enabled row, then the owner disabled it before claim.
    row={key:'synthetic' for key in REQUIRED_FIELDS}
    row.update({'Task Loop ID':'SYNTHETIC-WAVE1-PAUSE','Enabled':'TRUE','Execution Mode':'Autonomous',
                'Claim Version':'1','Claim Token':'','Claimed By':'','Current Run ID':'',
                'Occurrence ID':'SYNTHETIC-OCCURRENCE','Effective Ready At':''})
    item=SimpleNamespace(task_id=row['Task Loop ID'],payload=dict(row))
    assert fresh_execution_decision(item.payload).ready
    row['Enabled']='FALSE'
    assert not fresh_execution_decision(row).ready
    run_headers=['Run ID','Pipeline ID','Run Type','Status','Lock Owner','Lock Acquired','Lock Expires','Preflight Status','Schema Version','Source Boundary Start','Source Boundary End','Commit Verified','Last Error','Updated']
    claim_headers=['Execution Status','Claimed By','Claim Token','Claim Version','Claimed At','Claim Expires At','Last Heartbeat At','Current Run ID']
    reservations=[];writes=[]
    class RunTable:
        def records(self):return [dict(r) for r in reservations]
        def append(self,values):
            reservations.append(dict(zip(run_headers,values)));return "'Synthetic Run Control'!A2:N2"
        def exact_record(self,expected):
            matches=[r for r in reservations if all(r.get(k)==v for k,v in expected.items())]
            return (2,matches[0]) if len(matches)==1 else None
    class TaskTable:
        def update_row(self,index,values,start,end):
            assert (index,start,end)==(2,'T','AA')
            updates={k:str(v) for k,v in zip(claim_headers,values)}
            row.update(updates);writes.append(updates)
    with tempfile.TemporaryDirectory(prefix='ecos-wave1-pause-probe-') as directory:
        fake=SimpleNamespace(node_root=Path(directory),claim_lease=timedelta(seconds=120),
            run=RunTable(),task=TaskTable(),reservations={},_find=lambda _: (2,dict(row)))
        with patch.object(legacy.time,'sleep',lambda _:None):
            claim=legacy.ResidentGovernedDispatcher.claim(fake,item,'SYNTHETIC-RESIDENT','SYNTHETIC-RUN')
        assert claim is not None and len(writes)==1 and row['Enabled']=='FALSE'
        owned=legacy.ResidentGovernedDispatcher._owned(fake,item,claim,'SYNTHETIC-RUN')
        delegated=legacy.ResidentGovernedDispatcher._validate_delegated_claim(fake,
            task_loop_id=item.task_id,occurrence_id=row['Occurrence ID'],run_id='SYNTHETIC-RUN',
            claimed_by='SYNTHETIC-RESIDENT',claim_token=claim.token,claim_version=claim.version)
        assert owned[1]['Enabled']=='FALSE' and delegated['verified']
    return {'status':'reproduced','installed_dispatcher_sha256':hashlib.sha256((SHARED/'ecos_runtime/resident_governed.py').read_bytes()).hexdigest(),
            'fresh_selector_rejects_disabled':True,'selected_then_disabled_row_still_claimed':True,
            'disabled_claim_passes_owned_check':True,'disabled_claim_passes_provider_claim_guard':True,
            'production_reads':False,'production_writes':False,'provider_calls':False,
            'meaning':'Enabled FALSE is a selection gate, not a final claim/provider authority fence for a previously selected item.'}
if __name__=='__main__':print(json.dumps(probe()))
