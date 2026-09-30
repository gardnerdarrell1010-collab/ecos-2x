"""Read-only A029-B compatibility and captured-source aggregate comparison."""
from pathlib import Path
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1];SHARED=Path(r'D:\ECOS\Node\runtime\releases\slots\1.0.011')
sys.dont_write_bytecode=True;sys.path[:0]=[str(ROOT),str(ROOT/'src'),str(ROOT/'scripts'),str(SHARED)]
from google.oauth2 import service_account
from googleapiclient.discovery import build
from ecos_runtime import staffing_history as history
from ecos_runtime.staffing_history_io import read,table,SOURCE_NAME,SUMMARY_NAME
from runtime.resident2x.toast_wave1 import compatible_bytes
credentials=service_account.Credentials.from_service_account_file(r'D:\ECOS\Credentials\ecos-resident-ada.json',scopes=['https://www.googleapis.com/auth/drive.readonly','https://www.googleapis.com/auth/spreadsheets.readonly'])
sheets=build('sheets','v4',credentials=credentials,cache_discovery=False,static_discovery=False)
drive=build('drive','v3',credentials=credentials,cache_discovery=False,static_discovery=False)
dispatcher=SimpleNamespace(service=sheets,spreadsheet_id='1LF0isNKZBgEbr8E_pzekSWJ8-iXGfGn3e3xteKuivu0',provider_tools=SimpleNamespace(_service=lambda _:drive))
source,identity=read(dispatcher,SOURCE_NAME);previous,_=read(dispatcher,SUMMARY_NAME)
forecast=table(dispatcher,'Forecast Performance').records()
report={'status':'passed','provider_calls':False,'production_writes':False,'consumer_code_changed':False,'windows':[]}
for path in sorted((ROOT/'.local/wave1-shadow-source').glob('2026-*.json')):
    frozen=json.loads(path.read_text());as_of=datetime.fromisoformat(frozen['as_of']);day=path.stem
    expected,_=history.normalize(frozen['raw'],as_of.astimezone().date(),{'sha256':history.digest(frozen['raw']),'verified_at':as_of.isoformat()},source)
    actual=json.loads(compatible_bytes(history,expected,as_of))
    assert all(d<as_of.astimezone().date().isoformat() and v['status']=='CLOSED_ACTUALS' for d,v in actual['dates'].items())
    assert actual['dates'][day]['material_hash']==frozen['normalized']['dates'][day]['material_hash']
    def measures(x):
        result={}
        for row in x['dates'][day]['rows']:
            for key,value in row['measures'].items():
                if isinstance(value,(int,float)) and not isinstance(value,bool):result[key]=result.get(key,Decimal(0))+Decimal(str(value))
        return result
    assert measures(actual)==measures(expected)
    assert actual['dates'][day]['labor_time_entries']==expected['dates'][day]['labor_time_entries']
    actual_summary,counts=history.summarize(actual,identity,forecast,previous)
    expected_summary,_=history.summarize(expected,identity,forecast,previous)
    assert actual_summary==expected_summary
    replay,replay_counts=history.summarize(actual,identity,forecast,actual_summary)
    assert replay==actual_summary and replay_counts['outcome']=='VERIFIED_NOOP'
    report['windows'].append({'business_date':day,'normalized_values':True,'aggregate_totals':True,'labor_values':True,
        'material_hash':True,'unchanged_a029b_calculation':True,'unchanged_a029b_noop_replay':True,
        'feature_rows':len(actual_summary['rows']),'canonical_bytes_hash':hashlib.sha256(compatible_bytes(history,expected,as_of)).hexdigest()})
(ROOT/'.local/wave1-shadow-source/compatibility-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
