"""Owner-authorized 1.x checkpoint and existing maintenance fence; no claim replay."""
import sys, json, hashlib, datetime
from pathlib import Path
sys.dont_write_bytecode=True
sys.path.insert(0, r'D:\ECOS\Node\runtime\releases\slots\1.0.011')
from google.oauth2 import service_account
from googleapiclient.discovery import build
SID='1LF0isNKZBgEbr8E_pzekSWJ8-iXGfGn3e3xteKuivu0'
KEY='ECOS_TASK_LOOP_MAINTENANCE_MODE'

def stamp(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def save(path,obj): path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
def main():
    dest=Path(sys.argv[1]);phase=sys.argv[2]
    assert dest.is_dir() and phase in ('before','after')
    cred=service_account.Credentials.from_service_account_file(r'D:\ECOS\Credentials\ecos-resident-ada.json',scopes=['https://www.googleapis.com/auth/spreadsheets'])
    api=build('sheets','v4',credentials=cred,cache_discovery=False).spreadsheets()
    meta=api.get(spreadsheetId=SID,fields='spreadsheetId,properties(title),sheets(properties)').execute(num_retries=3)
    assert meta['spreadsheetId']==SID and meta['properties']['title']=='ECOS Master Database'
    props={s['properties']['title']:s['properties'] for s in meta['sheets']}
    selected=['System Bootstrap','Sheet Registry','Settings','Task Loop','Tasks','Projects','Run Control','Ingestion State','Communications','Notification Queue','Notification Deliveries','Exceptions','Workflow Dependencies','Artifacts','Facts','AI Memory','Authoritative Files']
    ranges=[]
    for title in selected:
        p=props[title];n=p['gridProperties']['columnCount'];col=''
        while n:n,k=divmod(n-1,26);col=chr(65+k)+col
        ranges.append(f"'{title}'!A1:{col}{p['gridProperties']['rowCount']}")
    began=stamp();values=[]
    for i in range(0,len(ranges),4):
        values.extend(api.values().batchGet(spreadsheetId=SID,ranges=ranges[i:i+4]).execute(num_retries=3)['valueRanges'])
    snapshot=dict(zip(selected,values));save(dest/(phase+'-governed.json'),{'started_at':began,'finished_at':stamp(),'sources':snapshot})
    rows=snapshot['Settings'].get('values',[])
    matches=[(i+1,r) for i,r in enumerate(rows) if r and r[0]==KEY]
    assert len(matches)==1,'maintenance_identity'
    row,record=matches[0];assert record[5]=='TRUE' and record[3] in ('TRUE','FALSE'),'maintenance_preimage'
    cell=f"'Settings'!D{row}"
    if phase=='before':
        native=api.get(spreadsheetId=SID,ranges=[cell],includeGridData=True,fields='sheets(data(rowData(values(userEnteredValue,dataValidation,userEnteredFormat))))').execute(num_retries=3)
        save(dest/'maintenance-preimage.json',{'row':row,'record':record,'native':native})
        value=native['sheets'][0]['data'][0]['rowData'][0]['values'][0]
        assert 'formulaValue' not in value.get('userEnteredValue',{}),'maintenance_formula'
        validation=value.get('dataValidation',{}).get('condition',{})
        assert not validation or validation.get('type') in ('BOOLEAN','ONE_OF_LIST'),'maintenance_validation'
        if validation.get('type')=='ONE_OF_LIST':assert 'TRUE' in [v.get('userEnteredValue') for v in validation.get('values',[])],'maintenance_allowed_value'
        fresh=api.values().get(spreadsheetId=SID,range=f"'Settings'!A{row}:H{row}").execute()['values'][0]
        assert fresh==record,'maintenance_changed'
        entered={'boolValue':True} if 'boolValue' in value.get('userEnteredValue',{}) else {'stringValue':'TRUE'}
        api.batchUpdate(spreadsheetId=SID,body={'requests':[{'updateCells':{'range':{'sheetId':props['Settings']['sheetId'],'startRowIndex':row-1,'endRowIndex':row,'startColumnIndex':3,'endColumnIndex':4},'rows':[{'values':[{'userEnteredValue':entered}]}],'fields':'userEnteredValue'}}]}).execute()
    check=api.values().get(spreadsheetId=SID,range=f"'Settings'!A{row}:H{row}").execute()['values'][0]
    assert check[0]==KEY and check[3]=='TRUE','maintenance_readback'
    table=snapshot['Task Loop']['values'];head=table[0]
    claims=[]
    for raw in table[1:]:
        r=dict(zip(head,raw))
        if r.get('Claimed By'):claims.append({k:r.get(k) for k in ('Task Loop ID','Claimed By','Current Run ID','Claim Expires At','Execution Status')})
    save(dest/(phase+'-summary.json'),{'checkpoint_at':stamp(),'maintenance':True,'claims':claims,'provider_outcomes':'RECONCILIATION_REQUIRED_NO_REPLAY','snapshot_sha256':hashlib.sha256((dest/(phase+'-governed.json')).read_bytes()).hexdigest()})

if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('CheckpointErrorType='+type(exc).__name__)
        raise SystemExit(1)
