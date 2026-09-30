"""Bounded frozen Gmail backlog assessment; no provider writes or task migration."""
import json,sys
from pathlib import Path
from datetime import datetime,timezone
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'src'),str(ROOT/'scripts')]
from resident2x_acceptance import hosted_admin,secure_directory

def main():
 connect,_=hosted_admin();items=[]
 with connect() as db:
  rows=db.execute("select b.id,b.column_names,r.source_locator,r.raw_hash,r.raw_value from ecos_migration.raw_source_row r join ecos_migration.raw_migration_batch b on b.id=r.batch_id where b.source_family='Tasks'").fetchall()
  for batch,columns,locator,digest,raw in rows:
   values=raw.get('values',[]);row=dict(zip(columns,values))
   if 'gmail' not in str(row.get('Source Type','')).lower():continue
   if str(row.get('Status','')).lower().startswith(('complete','cancel')):continue
   # Gmail URLs alone do not establish both immutable provider IDs or prove
   # absence of a prior effect. Preserve for authoritative reconciliation.
   items.append({'batch_id':str(batch),'source_locator':locator,'source_hash':digest,
                 'legacy_task_id':row.get('Task ID'),'disposition':'HELD_UNVERIFIED_IDENTITY_AND_EFFECT',
                 'completion_evidence_present':bool(row.get('Completion Evidence'))})
 state=ROOT/'.local/gmail-enrollment'/('backlog-assessment-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
 secure_directory(state)
 (state/'assessment.json').write_text(json.dumps(items,indent=2))
 result={'CandidatePendingGmailTasks':len(items),'VerifiedEligible':0,'Released':0,'Held':len(items),'ProviderEffectsReplayed':0,'CompleteReenqueueImplementation':False}
 (state/'summary.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))

if __name__=='__main__':main()
