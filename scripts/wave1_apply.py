"""Guarded owner-authorized forward authority migration; no domain transfer."""
import argparse,hashlib,json,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'src'),str(ROOT/'scripts')]
from resident2x_acceptance import hosted_admin,secure_directory
from migrations import inventory,plan
from runtime.resident2x.executor import save

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    connect,_=hosted_admin()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')
    state=ROOT/'.local'/('wave1-authority-'+stamp);secure_directory(state)
    items=inventory(ROOT/'db/migrations')[:23]
    with connect() as db:
        db.execute('select pg_advisory_xact_lock(684026,2)')
        history=[dict(zip(('version','name','sha256'),r)) for r in db.execute('select version,name,sha256 from ecos_meta.schema_migration order by version')]
        pending=plan(items,history)
        assert [r['version'] for r in pending] in ([21,22,23],[23],[]),'unexpected migration head'
        identity=db.execute('select to_jsonb(d) from ecos_meta.database_identity d').fetchone()[0]
        active=db.execute("select count(*) from ecos.work_claim where state='active' and expires_at>clock_timestamp()").fetchone()[0]
        live=db.execute("select count(*) from ecos.v_executor_status where status='available'").fetchone()[0]
        assert active==0 and live==0,'active 2x work or executor prevents forward migration'
        definitions=db.execute("select n.nspname,p.proname,pg_get_functiondef(p.oid) from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname in ('ecos','ecos_meta') and p.prokind='f'").fetchall()
        save(state/'preimage.json',{'identity':identity,'history':history,'active_claims':active,'live_executors':live,'functions':definitions})
        if not args.apply:
            print(json.dumps({'status':'preflight_passed','pending':[r['name'] for r in pending]}));return
        for item in pending:
            db.execute(item['sql'],prepare=False)
            db.execute('insert into ecos_meta.schema_migration(version,name,sha256) values(%s,%s,%s)',(item['version'],item['name'],item['sha256']))
    with connect() as db:
        identity=db.execute('select to_jsonb(d) from ecos_meta.database_identity d').fetchone()[0]
        domains=db.execute('select domain,owner,epoch from ecos_meta.domain_authority order by domain').fetchall()
        head=db.execute('select max(version) from ecos_meta.schema_migration').fetchone()[0]
        assert (identity['environment'],identity['authority'],identity['provider_effects_enabled'])==('production','domain_scoped',True)
        assert dict((r[0],r[1]) for r in domains)=={'synthetic.acceptance':'2X','toast.acquisition':'1X','staffing.features':'1X'}
        report={'status':'passed','migration_head':head,'database_identity':identity,'domains':domains,
                'applied':[dict((k,r[k]) for k in ('version','name','sha256')) for r in pending],
                'domain_transfer':False,'ecos1x_writes':False,'provider_effects':False}
        save(state/'result.json',report);print(json.dumps(report))
if __name__=='__main__':main()
