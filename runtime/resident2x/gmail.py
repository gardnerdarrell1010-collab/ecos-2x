"""Gmail draft stage for the existing Resident lifecycle; external sends remain gated."""
import base64
from email.message import EmailMessage
import hashlib
import json
from pathlib import Path
import sys
from uuid import uuid4

from ecos.adapters.gmail import GmailDraftAdapter, ReconciliationRequired
from ecos.core.contracts import content_hash
from runtime.resident2x.executor import save


def handler(config):
    def execute(runtime, package, guard):
        occurrence=package['occurrence']['id']
        with runtime.connect() as db:
            value=db.execute('select ecos.gmail_read(%s::uuid)',(occurrence,)).fetchone()[0]
        command=value['command']; draft=value['draft_request']; original=draft['request']
        if command['command_type'] != 'draft.create' or content_hash(original)!=command['request_hash']:
            raise ValueError('gmail_draft_request_mismatch')
        message=EmailMessage()
        if original['to']:message['To']=', '.join(original['to'])
        message['Subject']=original['subject'];message['In-Reply-To']=original['in_reply_to']
        message['References']=original['in_reply_to'];message['Message-ID']='<ecos-'+command['id']+'@ecos.invalid>'
        message.set_content(original['body'])
        raw=message.as_bytes();encoded=base64.urlsafe_b64encode(raw).decode()
        wire={'command_type':command['command_type'],'account_scope':command['account_scope'],
              'request':{'raw':encoded,'thread_id':original['thread_id']},'request_hash':hashlib.sha256(raw).hexdigest()}
        journal=runtime.root/'gmail-effects'/(command['id']+'.json')

        class Gate:
            def begin(self, _):
                guard()
                if journal.exists():
                    saved=json.loads(journal.read_text())
                    if saved.get('status')=='completed':return {'disposition':'completed','result':saved['result']}
                    raise ReconciliationRequired('gmail_saved_attempt_requires_reconciliation')
                # Save intent before the governed begin; loss at either boundary is held.
                save(journal,{'status':'starting','command_id':command['id'],'occurrence_id':occurrence})
                response=runtime.invoke('gmail.dispatch.begin',{'fence':package['fence'],'command_id':command['id']},key='gmail-begin:'+str(uuid4()))
                attempt=response['data']
                if attempt['request_hash']!=content_hash(original):raise ValueError('gmail_attempt_hash_mismatch')
                save(journal,{'status':'started','attempt':attempt})
                return attempt
            def finish(self, _, attempt, result):
                guard()
                response=runtime.invoke('gmail.dispatch.finish',{'fence':package['fence'],'command_id':command['id'],'attempt_id':attempt['attempt_id'],'readback':result},key='gmail-finish:'+command['id'])
                with runtime.connect() as db:
                    confirmed=db.execute('select ecos.gmail_read(%s::uuid)',(occurrence,)).fetchone()[0]
                if confirmed['draft_request']['readback']!=result or confirmed['command']['outcome']!='reconciled':raise ValueError('gmail_sql_readback_mismatch')
                save(journal,{'status':'completed','attempt':attempt,'result':result})

        sys.path.append(config['google_client_library'])
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        secret=json.loads(Path(config['gmail_credential_file']).read_text())
        if secret['account_scope']!=command['account_scope']:raise ValueError('gmail_mailbox_mismatch')
        credentials=Credentials(token=None,refresh_token=secret['refresh_token'],token_uri=secret['token_uri'],client_id=secret['client_id'],client_secret=secret['client_secret'],scopes=secret['scopes'])
        service=build('gmail','v1',credentials=credentials,cache_discovery=False,static_discovery=False)
        result=GmailDraftAdapter(service,command['account_scope']).draft(wire,Gate())
        return {'content_hash':content_hash(result),'source_references':package['source_references'],
                'provider_business_mutations':True,'sent':False,'draft_id':result['draft_id'],'readback_verified':True}
    return execute


if __name__ == '__main__':
    import argparse
    from runtime.resident2x.executor import Resident
    from runtime.resident2x.connection import connection_factory
    parser=argparse.ArgumentParser();parser.add_argument('--config',type=Path,required=True);parser.add_argument('--max-cycles',type=int,default=0)
    args=parser.parse_args();config=json.loads(args.config.read_text())
    runtime=Resident(config,connection_factory(config),{'gmail_draft':handler(config)})
    runtime.run(args.max_cycles)
