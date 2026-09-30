"""Wave 1 adapter: reuse pinned 1.x acquisition/normalization/projection logic.

No legacy execute(), Sheets control, Drive publish, or staffing feature execution.
The only Toast POST allowed is authentication; all business endpoints are GET.
"""
from datetime import date, datetime, timedelta, timezone
import hashlib
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import os

PINNED = {
    'toast_refresh_worker.py': '8d72fe8eec9ebeed20bf7c0e813c98d3888ed00631014824348c016dbd4e97c7',
    'staffing_history.py': '189d6af66ac1fd96bf6a38ddc80cc427fe9462c29bd139b96e5af653da77586a',
    'dashboard_source_c_worker.py': '8f1449b7bd862d4b0a8c75764f9eb34d45b013e4ad8db3ec47633f2daa9d2fd2',
}

def modules(root):
    root=Path(root).resolve()
    for name,digest in PINNED.items():
        if hashlib.sha256((root/'ecos_runtime'/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('wave1_shared_source_changed')
    sys.dont_write_bytecode=True
    sys.path.insert(0,str(root))
    values=[]
    for name in PINNED:
        module=importlib.import_module('ecos_runtime.'+name[:-3])
        if Path(module.__file__).resolve()!=root/'ecos_runtime'/name:
            raise ValueError('wave1_shared_source_origin_mismatch')
        values.append(module)
    return tuple(values)

def source_dates(today, business_date):
    day=date.fromisoformat(business_date)
    if day>=today:raise ValueError('closed_date_required')
    return day.strftime('%Y%m%d')

def acquire(toast, dashboard, credential_reference, business_date, as_of, guard=lambda:None):
    """Caller supplies the same explicit window/as-of for both parity executions."""
    today=as_of.astimezone().date()
    bd=source_dates(today,business_date)
    dispatcher=SimpleNamespace(credential_base_references={
        'ECOS_NODE_GOOGLE_SERVICE_ACCOUNT_REFERENCE':Path(credential_reference)})
    guard();token=toast._login(toast._credential(dispatcher))
    guard();restaurant=toast._restaurant(token);rid=restaurant['restaurantGuid']
    start=today-timedelta(days=today.weekday());end=today+timedelta(days=21)
    def get(path,query):
        guard()
        return toast._request('GET',path,token=token,restaurant=rid,query=query)
    # Preserve the installed schedule windows and semantics exactly.
    schedule={
        'acceptance_2026_09_07_through_2026_09_13':get('/labor/v1/shifts',{'startDate':'2026-09-07T00:00:00.000-0000','endDate':'2026-09-14T00:00:00.000-0000'}),
        'current_21_day_horizon':get('/labor/v1/shifts',{'startDate':start.strftime('%Y-%m-%dT%H:%M:%S.000-0000'),'endDate':end.strftime('%Y-%m-%dT%H:%M:%S.000-0000')})}
    guard();payments=toast._payment_details(token,rid,bd)
    raw={'schema_version':'ECOS-TOAST-OPERATIONAL-CACHE-1','generated_at':as_of.isoformat(),
        'restaurant':{'guid':rid,'name':restaurant.get('restaurantName')},
        'coverage':{'closed_actuals_through':business_date,'schedule_start':start.isoformat(),'schedule_through':end.isoformat()},
        'schedule':schedule,'closed_actuals':{'business_date':bd,'payments':payments,
            'cash_entries':get('/cashmgmt/v1/entries',{'businessDate':bd}),
            'deposits':get('/cashmgmt/v1/deposits',{'businessDate':bd}),
            'time_entries':get('/labor/v1/timeEntries',{'businessDate':bd})}}
    # A047 has a different temporal contract: prior/current day is deliberately partial.
    dates=[(today-timedelta(days=1)).strftime('%Y%m%d'),today.strftime('%Y%m%d')]
    families={name:dashboard._read_family(path,dates,token,rid,paged=paged,guard=guard)
              for name,path,paged in [('orders','/orders/v2/ordersBulk',True),('labor','/labor/v1/timeEntries',False),('deposits','/cashmgmt/v1/deposits',False)]}
    return raw,families,restaurant,dates

def transform(history,dashboard,raw,families,restaurant,dates,as_of,previous=None):
    normalized,changed=history.normalize(raw,as_of.astimezone().date(),
        {'sha256':history.digest(raw),'verified_at':as_of.isoformat()},previous)
    projection=dashboard.build_snapshot(families,restaurant,dates,as_of)
    if len(json.dumps(projection,ensure_ascii=False))>=40000:
        raise ValueError('dashboard_projection_budget_exceeded')
    return normalized,changed,projection

def compatible_bytes(history,normalized,as_of):
    """Exact existing publication format; no file write or registry mutation."""
    value=dict(normalized);value.pop('content_hash',None)
    value['generated_at']=as_of.isoformat();value['content_hash']=history.digest(value)
    return history.encode(value)

def handler(config):
    """Actual Resident stage. SQL owns checkpoint/claim; local files preserve acquisition bytes."""
    toast,history,dashboard=modules(config['wave1']['shared_root'])
    def execute(runtime,package,guard):
        from .executor import save
        occurrence=package['occurrence']['id']
        stage_input=package['input']
        if config.get('domain')!='toast.acquisition' or config.get('execution_mode') not in ('shadow','production'):
            raise ValueError('wave1_domain_required')
        # This capability acquires provider data and commits SQL only. It neither
        # publishes a legacy compatibility artifact nor authorizes provider writes.
        # PostgreSQL still enforces principal/domain scope and the current fence.
        if config.get('provider_effects_enabled') is not False:
            raise ValueError('toast_acquisition_requires_read_only_provider')
        directory=runtime.root/'toast';directory.mkdir(exist_ok=True)
        captured=directory/(occurrence+'.json')
        def crash(point):
            requested=config.get('wave1',{}).get('acceptance_crash')
            marker=directory/(occurrence+'.'+point)
            if config['execution_mode']=='shadow' and requested==point and not marker.exists():
                marker.write_text('synthetic crash injection',encoding='utf-8')
                os._exit(77)
        if captured.exists():
            data=json.loads(captured.read_text(encoding='utf-8'))
        else:
            as_of=datetime.fromisoformat(stage_input['as_of'])
            guard()
            raw,families,restaurant,dates=acquire(toast,dashboard,config['wave1']['credential_reference'],stage_input['business_date'],as_of,guard)
            normalized,changed,projection=transform(history,dashboard,raw,families,restaurant,dates,as_of)
            day=stage_input['business_date']
            data={'restaurant_hash':hashlib.sha256(restaurant['restaurantGuid'].encode()).hexdigest(),
                  'business_date':day,'observation_json':history.encode(normalized['dates'][day]).decode(),
                  'projection_json':dashboard.serialize(projection),'source_hash':history.digest(raw)}
            save(captured,data)
        crash('after_acquisition')
        guard()
        with runtime.connect() as db:
            checkpoint=db.execute('select ecos.toast_checkpoint_read(%s)',(data['restaurant_hash'],)).fetchone()[0]
        response=runtime.invoke('toast.batch.commit',dict(data,fence=package['fence'],expected_checkpoint_version=(checkpoint or {}).get('record_version') or 0),
                                key=occurrence+':toast-batch:'+package['fence']['claim_id'])
        crash('after_commit')
        with runtime.connect() as db:
            committed=db.execute('select ecos.toast_readback(%s)',(occurrence,)).fetchone()[0]
        if not committed or any(committed[k]!=v for k,v in data.items()) or committed['content_hash']!=response['data']['content_hash']:
            raise ValueError('toast_independent_readback_mismatch')
        task=runtime.read('task',package['task']['id'])
        return {'content_hash':committed['content_hash'],'batch_id':committed['id'],
                'business_date':data['business_date'],'source_references':[runtime.reference('task',task)],
                'sql_readback_verified':True,'execution_mode':config['execution_mode'],'provider_business_mutations':False}
    return execute
