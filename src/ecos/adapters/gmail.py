"""Gmail provider boundary: immutable source identity, draft readback, no send API.

The caller supplies an authenticated Gmail API service and governed effect gate.
No credentials, SQL, semantic decisions or retries are embedded in this adapter.
"""
import base64
import hashlib
from email import policy
from email.parser import BytesParser


class ReconciliationRequired(RuntimeError):
    pass


def decode_raw(raw):
    if not isinstance(raw, str) or len(raw) > 2_000_000:
        raise ValueError('invalid_gmail_raw')
    return base64.b64decode(raw + '=' * (-len(raw) % 4), altchars=b'-_', validate=True)


def message_evidence(account, message):
    """Preserve provider IDs and exact raw bytes; never derive Gmail IDs from headers."""
    if not account or not message.get('id') or not message.get('threadId') or not message.get('raw'):
        raise ValueError('incomplete_gmail_identity')
    raw = decode_raw(message['raw'])
    return {'provider': 'gmail', 'account_scope': account,
            'message_id': message['id'], 'thread_id': message['threadId'],
            'history_id': message.get('historyId'), 'internal_date': message.get('internalDate'),
            'raw': message['raw'], 'raw_sha256': hashlib.sha256(raw).hexdigest(),
            'label_ids': sorted(message.get('labelIds', []))}


def mime_identity(raw):
    """Gmail can normalize MIME bytes. Compare decoded content and identity headers."""
    parsed = BytesParser(policy=policy.default).parsebytes(decode_raw(raw))
    # Gmail assigns its own Message-ID to a saved draft. Provider IDs are
    # independently checked below; reply identity and all recipients remain exact.
    headers = {name: str(parsed.get(name, '')) for name in
               ('To', 'Cc', 'Bcc', 'Subject', 'In-Reply-To', 'References')}
    parts = []
    for part in parsed.walk():
        if not part.is_multipart():
            payload = part.get_payload(decode=True) or b''
            if part.get_content_maintype() == 'text':
                payload = payload.replace(b'\r\n', b'\n')
            parts.append((part.get_content_type(), part.get_filename(),
                          hashlib.sha256(payload).hexdigest()))
    return headers, parts


class GmailDraftAdapter:
    def __init__(self, service, account):
        self.service, self.account = service, account

    def _verify_account(self):
        profile = self.service.users().getProfile(userId='me').execute(num_retries=0)
        if profile.get('emailAddress', '').casefold() != self.account.casefold():
            raise ValueError('gmail_account_mismatch')

    def read(self, message_id):
        self._verify_account()
        value = self.service.users().messages().get(userId='me', id=message_id, format='raw').execute(num_retries=0)
        if value.get('id') != message_id:
            raise ValueError('gmail_message_mismatch')
        return message_evidence(self.account, value)

    def draft(self, command, gate):
        """Gate must durably authorize/record an attempt BEFORE any Gmail mutation.

        begin returns dispatch, completed, or hold; ambiguous attempts are never replayed.
        finish commits provider result/readback via the existing governed boundary.
        """
        if command['command_type'] not in ('draft.create', 'draft.update'):
            raise ValueError('gmail_draft_only')
        if command['account_scope'].casefold() != self.account.casefold():
            raise ValueError('gmail_account_mismatch')
        request = command['request']
        expected = mime_identity(request['raw'])
        if hashlib.sha256(decode_raw(request['raw'])).hexdigest() != command['request_hash']:
            raise ValueError('gmail_request_hash_mismatch')
        if command['command_type'] == 'draft.update' and not request.get('draft_id'):
            raise ValueError('gmail_draft_id_required')
        self._verify_account()
        decision = gate.begin(command)
        if decision['disposition'] == 'completed':
            return decision['result']
        if decision['disposition'] not in ('dispatch', 'reconcile'):
            raise ReconciliationRequired('gmail_effect_held')
        drafts = self.service.users().drafts()
        message = {'raw': request['raw']}
        if request.get('thread_id'):
            message['threadId'] = request['thread_id']
        try:
            if decision['disposition'] == 'reconcile':
                created = {'id': decision['draft_id']}
            elif command['command_type'] == 'draft.create':
                created = drafts.create(userId='me', body={'message': message}).execute(num_retries=0)
            else:
                created = drafts.update(userId='me', id=request['draft_id'], body={'message': message}).execute(num_retries=0)
            if hasattr(gate, 'observe'):
                gate.observe(command, decision, {'draft_id': created['id']})
            actual = drafts.get(userId='me', id=created['id'], format='raw').execute(num_retries=0)
            if actual['id'] != created['id'] or mime_identity(actual['message']['raw']) != expected:
                raise ReconciliationRequired('gmail_draft_readback_mismatch')
            if request.get('thread_id') and actual['message']['threadId'] != request['thread_id']:
                raise ReconciliationRequired('gmail_thread_readback_mismatch')
            evidence = message_evidence(self.account, actual['message'])
            result = {'draft_id': actual['id'], 'message_id': evidence['message_id'],
                      'thread_id': evidence['thread_id'], 'readback_sha256': evidence['raw_sha256'],
                      'provider': 'gmail', 'account_scope': self.account, 'sent': False}
            gate.finish(command, decision, result)
            return result
        except Exception as exc:
            # An uncertain HTTP or SQL response is held, never treated as no effect.
            raise ReconciliationRequired('gmail_draft_outcome_requires_reconciliation') from exc
