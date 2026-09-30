"""Independent readback of the two authorized fresh Gmail acceptance fixtures."""
import sys,json,base64,hashlib
from pathlib import Path
from email.message import EmailMessage
r=Path('C:/ECOS/ecos-2x');sys.path[:0]=[str(r),str(r/'src'),str(r/'scripts'),'D:/ECOS/Node/runtime/releases/slots/1.0.011']
from resident2x_acceptance import hosted_admin
from ecos.adapters.gmail import mime_identity,decode_raw
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
s=json.loads((r/'.local/gmail-enrollment/oauth.json').read_text());v=json.loads((r/'.local/gmail-enrollment/functional-v2/fixtures.json').read_text());connect,_=hosted_admin()
c=Credentials(token=None,refresh_token=s['refresh_token'],token_uri=s['token_uri'],client_id=s['client_id'],client_secret=s['client_secret'],scopes=s['scopes'])
g=build('gmail','v1',credentials=c,cache_discovery=False,static_discovery=False)
pass_count=int(sys.argv[1]);assert pass_count in (1,2)
results=[]
with connect() as db:
 for n,item in enumerate(v['passes'][:pass_count],1):
  row=db.execute("select d.command_id,d.request,d.readback,c.outcome,p.state from ecos.gmail_draft_request d join ecos.provider_command c on c.id=d.command_id join ecos.communication_processing p on p.id=d.processing_id join ecos.work_occurrence o on o.id=p.occurrence_id where o.task_id=%s",(item['task_id'],)).fetchone()
  assert row and row[2] and row[3:] == ('reconciled','succeeded'),'Resident completion pending'
  cid,req,rb,*_=row
  states=db.execute('select state from ecos.work_occurrence where task_id=%s',(item['task_id'],)).fetchall();assert len(states)==3 and all(x==('succeeded',) for x in states)
  assert db.execute('select count(*) from ecos.provider_attempt where provider_command_id=%s',(cid,)).fetchone()==(1,)
  assert req['to']==[] and rb['sent'] is False and rb['account_scope']==s['account_scope']
  a=g.users().drafts().get(userId='me',id=rb['draft_id'],format='raw').execute(num_retries=0)
  assert a['message']['id']==rb['message_id'] and a['message']['threadId']==req['thread_id'] and 'SENT' not in a['message'].get('labelIds',[])
  m=EmailMessage();m['Subject']=req['subject'];m['In-Reply-To']=req['in_reply_to'];m['References']=req['in_reply_to'];m['Message-ID']='<ecos-'+str(cid)+'@ecos.invalid>';m.set_content(req['body'])
  assert mime_identity(base64.urlsafe_b64encode(m.as_bytes()).decode())==mime_identity(a['message']['raw'])
  assert hashlib.sha256(decode_raw(a['message']['raw'])).hexdigest()==rb['readback_sha256']
  results.append({'Occurrence':n,'Intake':'PASS','Semantic':'PASS','Approval':'PASS','ResidentCompletion':'PASS','IndependentGmailReadback':'PASS','ProviderCreateAttempts':1,'Recipients':0,'Sent':False})
(r/'.local/gmail-enrollment/functional-v2/final-readback.json').write_text(json.dumps(results,indent=2))
print(json.dumps(results))
