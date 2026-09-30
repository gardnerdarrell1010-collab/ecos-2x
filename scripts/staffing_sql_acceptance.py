"""Rollback-only SQL parity against the preserved deterministic staffing logic."""
import sys,json,math
from pathlib import Path
from datetime import date,timedelta
ROOT=Path('C:/ECOS/ecos-2x');sys.dont_write_bytecode=True;sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'src'),r'D:\ECOS\Node\runtime\releases\slots\1.0.011']
from resident2x_acceptance import hosted_admin
from psycopg.types.json import Jsonb
from runtime.resident2x.toast_wave1 import modules
_,history,_=modules('D:/ECOS/Node/runtime/releases/slots/1.0.011')
assert '--hosted' in sys.argv, 'Explicit --hosted authorization required'
sql=(ROOT/'db/migrations/000025_staffing_features.sql').read_text()
dates={}
for n in range(100):
    day=(date(2026,5,1)+timedelta(days=n)).isoformat()
    rows=[]
    for half in ('12:00','12:30'):
        rows.append({'business_date':day,'interval_start':day+'T'+half+':00-07:00','local_half_hour':half,
                     'measures':{'actual_sales':None,'payment_amount':None if n%7==0 else n*1.25,'clock_presence_hours':0.5},'source_ids':[],'labels':[]})
    dates[day]={'business_date':day,'status':'CLOSED_ACTUALS','rows':rows,'labor_time_entries':[],'availability':{},'material_hash':history.digest(rows)}
source={'dates':dates,'coverage_through':max(dates),'daypart_definitions':[]}
expected,_=history.summarize(source,{'file_id':'synthetic:parity'},[])
connect,_=hosted_admin();count=0
with connect() as db:
    try:
        existed=db.execute("select to_regprocedure('ecos_meta.staffing_statistics(text,text,text)') is not null").fetchone()[0]
        if not existed:db.execute(sql,prepare=False)
        for day,observation in dates.items():
            db.execute("insert into ecos.toast_closed_date(domain,execution_mode,restaurant_hash,business_date,observation,batch_id) values('synthetic.acceptance','synthetic',%s,%s,%s,null)",('e'*64,day,Jsonb(observation)))
        actual=db.execute("select ecos_meta.staffing_statistics('synthetic.acceptance','synthetic',%s)",('e'*64,)).fetchone()[0]
        assert len(actual['rows'])==len(expected['rows'])
        for a,e in zip(actual['rows'],expected['rows']):
            assert a['business_date']==e['business_date'] and a['interval_start']==e['interval_start']
            for window,stats in e['statistics'].items():
                for measure,values in stats.items():
                    for field in ('count','source_dates','mean','median','min','max','sample_stddev'):
                        left=a['statistics'][window][measure][field];right=values[field]
                        assert (math.isclose(left,right,rel_tol=1e-12,abs_tol=1e-12) if isinstance(right,float) else left==right),(window,measure,field)
                        count+=1
        report={'status':'passed','synthetic_days':len(dates),'feature_rows':len(actual['rows']),'parity_comparisons':count,'production_data_mutation':False,'transaction':'ROLLED_BACK'}
    finally:db.rollback()
with connect() as db:
    assert db.execute("select to_regprocedure('ecos_meta.staffing_statistics(text,text,text)')").fetchone()[0] is None if not existed else db.execute("select to_regprocedure('ecos_meta.staffing_statistics(text,text,text)') is not null").fetchone()[0]
    assert db.execute("select count(*) from ecos.toast_closed_date where restaurant_hash=%s",('e'*64,)).fetchone()[0]==0
print(json.dumps(report))
