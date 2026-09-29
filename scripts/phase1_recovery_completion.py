"""Explicit disposable PostgreSQL rebuild/restore acceptance; never a runtime service."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
from uuid import uuid4
import psycopg
from psycopg import sql
from migrations import inventory,render
from phase1_live_completion import SessionTarget,SECRET_REF

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from ecos.core.contracts import ContractStore
from ecos.core.export_verify import verify_inventory
SCHEMAS=['ecos','ecos_meta','ecos_migration']

def schema_inventory(db):
    db.execute('set search_path=pg_catalog')
    queries={
      'relations':"select n.nspname,c.relname,c.relkind from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname=any(%s) and c.relkind in ('r','v','i','S') order by 1,2,3",
      'columns':"select table_schema,table_name,column_name,data_type,is_nullable,column_default from information_schema.columns where table_schema=any(%s) order by table_schema,table_name,ordinal_position",
      'constraints':"select n.nspname,c.relname,k.conname,pg_get_constraintdef(k.oid) from pg_constraint k join pg_class c on c.oid=k.conrelid join pg_namespace n on n.oid=c.relnamespace where n.nspname=any(%s) order by 1,2,3",
      'functions':"select n.nspname,p.proname,pg_get_function_identity_arguments(p.oid),pg_get_functiondef(p.oid) from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname=any(%s) order by 1,2,3",
      'triggers':"select n.nspname,c.relname,t.tgname,pg_get_triggerdef(t.oid) from pg_trigger t join pg_class c on c.oid=t.tgrelid join pg_namespace n on n.oid=c.relnamespace where n.nspname=any(%s) and not t.tgisinternal order by 1,2,3"}
    result={}
    for name,query in queries.items():
        rows=db.execute(query,(SCHEMAS,)).fetchall()
        rows=[tuple(value.replace("\r\n","\n") if isinstance(value,str) else value for value in row) for row in rows]
        result[name]={'object_hashes':{str(row[:2]):hashlib.sha256(json.dumps(row,default=str).encode()).hexdigest() for row in rows},'count':len(rows),'sha256':hashlib.sha256(json.dumps(rows,default=str,separators=(',',':')).encode()).hexdigest()}
    return result

def data_inventory(db):
    tables=db.execute("select table_schema,table_name from information_schema.tables where table_schema=any(%s) and table_type='BASE TABLE' order by 1,2",(SCHEMAS,)).fetchall()
    result={}
    for ns,name in tables:
        query=sql.SQL("select count(*),encode(sha256(convert_to(coalesce(string_agg(to_jsonb(t)::text,E'\\n' order by to_jsonb(t)::text COLLATE \"C\"),''),'UTF8')),'hex') from {}.{} t").format(sql.Identifier(ns),sql.Identifier(name))
        count,digest=db.execute(query).fetchone()
        result[ns+'.'+name]={'rows':count,'sha256':digest}
    return result

def run_sql_suite(db):
    db.autocommit=True
    cur=db.execute((ROOT/'db/tests/phase1_transactional.sql').read_text(),prepare=False)
    results=[]
    while True:
        if cur.description:results+=cur.fetchall()
        if not cur.nextset():break
    checks=next(row[0] for row in results if row and isinstance(row[0],list))
    assert len(checks)>=31
    return checks

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--secret-materialization',required=True,type=Path)
    parser.add_argument('--pg-bin',required=True,type=Path)
    parser.add_argument('--runtime-root',required=True,type=Path)
    parser.add_argument('--openssl',required=True,type=Path)
    parser.add_argument('--report',required=True,type=Path)
    args=parser.parse_args()
    root=args.runtime_root.resolve();root.mkdir(parents=True,exist_ok=False)
    data=root/'data';pwfile=root/'init-password';log=root/'server.log'
    package=ROOT/'.local'/'phase1-completion'/root.name;package.mkdir(parents=True,exist_ok=False)
    local_password=secrets.token_urlsafe(32)
    source=SessionTarget(args.secret_materialization)
    report={'started_at':datetime.now(timezone.utc).isoformat(),'secret_reference':SECRET_REF,'runtime_kind':'disposable loopback PostgreSQL process; no Windows service','runtime_directory':str(root),'provider_calls_executed':False,'production_data_migrated':False}
    running=False
    def native(binary,arguments,env=None,timeout=180):
        command=[str(args.pg_bin/(binary+'.exe'))]+[str(a) for a in arguments]
        with tempfile.TemporaryFile(mode="w+",encoding="utf-8") as output:
            completed=subprocess.run(command,env=env,stdout=output,stderr=output,text=True,timeout=timeout,creationflags=subprocess.CREATE_NO_WINDOW)
            output.seek(0)
            completed.stdout=completed.stderr=output.read()
        if completed.returncode:
            message=completed.stderr.replace(local_password,'[REDACTED]').replace(source._password,'[REDACTED]')
            raise RuntimeError(binary+' failed: '+message[:2000])
        return completed.stdout.strip()
    def local(database='postgres',autocommit=False):
        return psycopg.connect(host='127.0.0.1',port=55432,dbname=database,user='postgres',password=local_password,sslmode='require',autocommit=autocommit,connect_timeout=10,options='-c timezone=UTC -c statement_timeout=90000')
    try:
        report['stage']='isolation_preflight'
        with socket.socket() as probe:probe.bind(('127.0.0.1',55432))
        account=os.environ.get('USERDOMAIN','')+'\\'+getpass.getuser()
        acl=subprocess.run(['icacls',str(root),'/inheritance:r','/grant:r',account+':(OI)(CI)F'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
        assert acl.returncode==0,'Could not restrict disposable runtime directory'
        pwfile.write_text(local_password,encoding='utf-8')
        report['stage']='initdb'
        try:native('initdb',['-D',data,'-U','postgres','--auth=scram-sha-256','--pwfile='+str(pwfile),'--encoding=UTF8','--locale=C'])
        finally:pwfile.unlink(missing_ok=True)
        cert=subprocess.run([str(args.openssl),'req','-x509','-nodes','-newkey','rsa:2048','-keyout',str(data/'server.key'),'-out',str(data/'server.crt'),'-days','1','-subj','/CN=localhost'],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
        assert cert.returncode==0,'Local TLS certificate generation failed'
        report['stage']='start_disposable_server'
        native('pg_ctl',['-D',data,'-l',log,'-o','-h 127.0.0.1 -p 55432 -c ssl=on -c max_connections=50 -c log_statement=none -c log_min_error_statement=panic','-w','start'])
        running=True
        with local(autocommit=True) as db:
            report['target_version']=db.execute('select version()').fetchone()[0]
            report['local_ssl']=db.pgconn.ssl_in_use
            db.execute('create database phase1_rebuild')
            db.execute('create database phase1_restore')
        report['stage']='clean_canonical_rebuild'
        migrations=inventory(ROOT/'db/migrations')
        chain=render(migrations).replace('\\set ON_ERROR_STOP on\n','',1)
        with local('phase1_rebuild',True) as db:
            assert db.execute('select count(*) from pg_namespace where nspname=any(%s)',(SCHEMAS,)).fetchone()[0]==0
            db.execute(chain,prepare=False)
            history=db.execute('select version,name,sha256 from ecos_meta.schema_migration order by version').fetchall()
            assert history==[(m['version'],m['name'],m['sha256']) for m in migrations]
            built=schema_inventory(db)
            checks=run_sql_suite(db)
            db.execute(chain,prepare=False)
            assert db.execute('select count(*) from ecos_meta.schema_migration').fetchone()[0]==len(migrations)
        report['mig01']={'status':'passed','migration_order':history,'schema_inventory':built,'transactional_checks':checks,'repeat_chain':'passed'}
        report['stage']='source_snapshot_and_export'
        with source.connect() as db:
            db.execute('set transaction isolation level repeatable read read only')
            assert db.execute('select environment,authority,provider_effects_enabled from ecos_meta.database_identity').fetchone()==('development','non_production',False)
            report['source_version']=db.execute('select version()').fetchone()[0]
            source_schema=schema_inventory(db)
            report['schema_differences']={k:{'source':source_schema[k],'rebuilt':built[k]} for k in built if source_schema[k]!=built[k]}
            assert source_schema==built,'Remote schema differs from canonical clean rebuild'
            source_data=data_inventory(db)
            snapshot=db.execute('select pg_export_snapshot()').fetchone()[0]
            env=dict(os.environ,PGHOST='aws-0-us-west-1.pooler.supabase.com',PGPORT='5432',PGUSER='postgres.loonpojawpfagzobxoko',PGDATABASE='postgres',PGPASSWORD=source._password,PGSSLMODE='require')
            dump=package/'ecos-development.dump'
            try:native('pg_dump',['--format=custom','--no-owner','--no-password','--snapshot='+snapshot,'--schema=ecos','--schema=ecos_meta','--schema=ecos_migration','--file',dump],env=env)
            finally:env.pop('PGPASSWORD',None)
        tool_version=native('pg_dump',['--version'])
        (package/'restore.md').write_text('Disposable PostgreSQL 17 target only. Create the NOLOGIN roles from roles.sql in a clean cluster. Restore the custom dump with pg_restore --no-owner --role=ecos_owner --exit-on-error into an empty database owned by ecos_owner. Supply credentials through ephemeral process environment, never command arguments. Verify checksums first, then compare counts/hashes and run db/tests/phase1_transactional.sql.\n',encoding='utf-8')
        (package/'verify.sql').write_text('select * from ecos_meta.database_identity;\nselect version,name,sha256 from ecos_meta.schema_migration order by version;\n',encoding='utf-8')
        roles=['ecos_owner','migration_runner','operations_api','executor','provider_adapter','auditor','backup_operator','read_only_analytics']
        (package/'roles.sql').write_text('\n'.join('create role '+role+' nologin noinherit nosuperuser nocreatedb nocreaterole noreplication nobypassrls;' for role in roles)+'\ngrant ecos_owner to migration_runner;\ngrant ecos_owner to postgres;\n',encoding='utf-8')
        manifest={'package_id':str(uuid4()),'schema_version':'1.0.0','created_at':datetime.now(timezone.utc).isoformat(),'database_schema_version':'1.0.0','migration_head':migrations[-1]['name'],'postgresql_version':report['source_version'],'tool_versions':{'pg_dump':tool_version,'exporter':'scripts/phase1_recovery_completion.py'},'files':[],'memory_head_ids':[],'restore_instructions_path':'restore.md','verification_queries_path':'verify.sql','secret_reference_names':[],'plaintext_secrets_included':False,'storage_control':'darrell_controlled'}
        for path,role in [(dump,'data'),(package/'restore.md','restore_instructions'),(package/'verify.sql','verification_queries'),(package/'roles.sql','configuration')]:
            raw=path.read_bytes();assert source._password.encode() not in raw,'Secret in export artifact'
            manifest['files'].append({'path':path.name,'size_bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'record_count':sum(x['rows'] for x in source_data.values()) if role=='data' else None,'role':role})
        ContractStore(ROOT).validate('export_manifest',manifest)
        assert verify_inventory(package,manifest)==4
        altered=json.loads(json.dumps(manifest));altered['files'][0]['sha256']='0'*64
        try:verify_inventory(package,altered)
        except ValueError:pass
        else:raise AssertionError('Corrupt manifest accepted')
        (package/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
        report['stage']='portable_restore'
        with local(autocommit=True) as db:db.execute('alter database phase1_restore owner to ecos_owner')
        env=dict(os.environ,PGHOST='127.0.0.1',PGPORT='55432',PGUSER='postgres',PGDATABASE='phase1_restore',PGPASSWORD=local_password,PGSSLMODE='require')
        try:native('pg_restore',['--no-owner','--role=ecos_owner','--exit-on-error','--no-password','--dbname=phase1_restore',dump],env=env)
        finally:env.pop('PGPASSWORD',None)
        with local('phase1_restore',True) as db:
            restored_schema=schema_inventory(db);restored_data=data_inventory(db)
            assert restored_schema==source_schema,'Restored objects differ'
            report['data_hash_differences']={k:{'source':source_data[k],'restored':restored_data.get(k)} for k in source_data if source_data[k]!=restored_data.get(k)}
            assert restored_data==source_data,'Restored row counts/hashes differ'
            restored_checks=run_sql_suite(db)
        report['rest01']={'status':'passed','dump_format':'PostgreSQL custom','tool_version':tool_version,'manifest':manifest,'manifest_sha256':hashlib.sha256((package/'manifest.json').read_bytes()).hexdigest(),'package_directory':str(package),'source_schema_inventory':source_schema,'restored_schema_inventory':restored_schema,'source_data_inventory':source_data,'restored_data_inventory':restored_data,'transactional_checks':restored_checks,'corrupt_manifest_rejected':True,'supabase_dependency_required':False}
        report['status']='passed'
    except Exception as exc:
        report.update(status='failed',error_type=type(exc).__name__,sqlstate=getattr(exc,'sqlstate',None))
        message=str(exc).replace(local_password,'[REDACTED]').replace(source._password,'[REDACTED]')
        report['diagnostic']=message[:2500]
    finally:
        if running:
            try:native('pg_ctl',['-D',data,'-m','fast','-w','stop']);report['disposable_server_stopped']=True
            except Exception as exc:report.update(status='failed',stop_error_type=type(exc).__name__)
        pwfile.unlink(missing_ok=True)
        local_password=None;source.clear()
        report['finished_at']=datetime.now(timezone.utc).isoformat()
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,indent=2,default=str)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('mig01','rest01','schema_differences')},indent=2))
    return 0 if report['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
