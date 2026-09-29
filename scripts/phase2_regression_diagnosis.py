"""Diagnose the second Phase 2 stop on a fresh disposable target; never repair it."""
import json,sys
from pathlib import Path
import phase2_integration as suite
from psycopg.types.json import Jsonb

report={'diagnostic_only':True,'persistent_access':False,'phase2_completed_checks':[]}
original=suite.tests

def diagnosed_tests(target):
    with target.connect() as db:
        report['migration_head']=db.execute('select max(version) from ecos_meta.schema_migration').fetchone()[0]
        report['identity']=db.execute('select row_to_json(i) from ecos_meta.database_identity i').fetchone()[0]
        report['attempt_limit_cases']=db.execute("select reasons, reasons-'attempt_limit', (reasons-'attempt_limit')<>'[]'::jsonb from (values ('[]'::jsonb),('[\"attempt_limit\"]'::jsonb),('[\"attempt_limit\",\"capability\"]'::jsonb)) v(reasons)").fetchall()
        report['repair_function_definition']=db.execute("select pg_get_functiondef('ecos_meta.reserve_resources()'::regprocedure)").fetchone()[0]
    diagnosed=False
    def trace(frame,event,arg):
        nonlocal diagnosed
        if Path(frame.f_code.co_filename).resolve()!=Path(suite.__file__).resolve():return trace
        if frame.f_code.co_name=='mark' and event=='return':report['phase2_completed_checks']=list(frame.f_locals['checks'])
        if frame.f_code.co_name=='good' and event=='exception' and not diagnosed and isinstance(arg[1],AssertionError):
            diagnosed=True
            report['failed_operation']=frame.f_locals['name']
            report['observed_result']=frame.f_locals['r']
            caller=frame.f_back
            while caller and caller.f_code.co_name!='tests':caller=caller.f_back
            report['failing_test_source_line']=caller.f_lineno
            fixture=caller.f_locals['f']
            occurrence=caller.f_locals['w']
            args=frame.f_locals['args'];ctx=fixture.request(args)['context']
            def state():
                with target.connect() as db:
                    return {'occurrence':db.execute('select state,attempt_count,record_version from ecos.work_occurrence where id=%s',(occurrence,)).fetchone(),'claims':db.execute('select count(*) from ecos.work_claim where occurrence_id=%s',(occurrence,)).fetchone()[0],'runs':db.execute('select count(*) from ecos.execution_run where occurrence_id=%s',(occurrence,)).fetchone()[0],'packages':db.execute('select count(*) from ecos.package_measurement where occurrence_id=%s',(occurrence,)).fetchone()[0]}
            report['after_governed_failure']=state()
            try:
                with target.connect() as db:
                    db.execute('set local role ecos_owner')
                    db.execute('select ecos_meta.apply_operation(%s,%s,%s)',(frame.f_locals['name'],Jsonb(ctx),Jsonb(args)))
                    db.rollback()
            except Exception as exc:
                report['raw_exception']={'type':type(exc).__name__,'sqlstate':getattr(exc,'sqlstate',None),'message':str(exc),'detail':getattr(exc.diag,'message_detail',None),'context':getattr(exc.diag,'context',None)}
            report['after_raw_diagnostic_rollback']=state()
        return trace
    sys.settrace(trace)
    try:return original(target)
    finally:sys.settrace(None)

suite.tests=diagnosed_tests
try:code=suite.main()
finally:
    output=Path(sys.argv[sys.argv.index('--report')+1]).with_name('repair-021-diagnosis.json')
    output.write_text(json.dumps(report,indent=2,default=str)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(report,default=str))
sys.exit(code)
