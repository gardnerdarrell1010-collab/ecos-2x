import base64
import hashlib
import unittest
from email.message import EmailMessage
from ecos.adapters.gmail import GmailDraftAdapter, ReconciliationRequired
from ecos.adapters.gmail_backlog import eligibility


class Call:
    def __init__(self, value): self.value = value
    def execute(self, **kwargs):
        assert kwargs == {'num_retries': 0}
        return self.value


class Gmail:
    def __init__(self, raw): self.raw, self.writes = raw, 0
    def users(self): return self
    def getProfile(self, **kwargs): return Call({'emailAddress': 'fixture@example.invalid'})
    def drafts(self): return self
    def create(self, **kwargs):
        self.writes += 1
        return Call({'id': 'draft-1'})
    def update(self, **kwargs): return self.create(**kwargs)
    def get(self, **kwargs):
        return Call({'id': 'draft-1', 'message': {'id': 'message-2', 'threadId': 'thread-1', 'raw': self.raw}})


class Gate:
    def __init__(self): self.started = False; self.finished = False
    def begin(self, command):
        if self.started: return {'disposition': 'hold'}
        self.started = True
        return {'disposition': 'dispatch'}
    def finish(self, command, attempt, result): self.finished = True


class GmailBoundaryTest(unittest.TestCase):
    def test_draft_readback_and_ambiguous_replay_hold(self):
        msg = EmailMessage(); msg['Subject'] = 'Synthetic draft'; msg.set_content('No delivery')
        data = msg.as_bytes(); raw = base64.urlsafe_b64encode(data).decode()
        provider, gate = Gmail(raw), Gate()
        command = {'command_type': 'draft.create', 'account_scope': 'fixture@example.invalid',
                   'request': {'raw': raw, 'thread_id': 'thread-1'}, 'request_hash': hashlib.sha256(data).hexdigest()}
        result = GmailDraftAdapter(provider, command['account_scope']).draft(command, gate)
        self.assertFalse(result['sent']); self.assertTrue(gate.finished)
        with self.assertRaises(ReconciliationRequired):
            GmailDraftAdapter(provider, command['account_scope']).draft(command, gate)
        self.assertEqual(provider.writes, 1)

    def test_gmail_assigned_message_id_and_text_line_endings(self):
        from email import policy
        original = EmailMessage(); original['Subject'] = 'Synthetic draft'
        original['Message-ID'] = '<ecos-synthetic@ecos.invalid>'
        original['In-Reply-To'] = '<source@example.invalid>'
        original.set_content('No delivery')
        raw = original.as_bytes()
        original.replace_header('Message-ID', '<provider-assigned@example.invalid>')
        observed = base64.urlsafe_b64encode(original.as_bytes(policy=policy.SMTP)).decode()
        provider, gate = Gmail(observed), Gate()
        command = {'command_type': 'draft.create', 'account_scope': 'fixture@example.invalid',
                   'request': {'raw': base64.urlsafe_b64encode(raw).decode(), 'thread_id': 'thread-1'},
                   'request_hash': hashlib.sha256(raw).hexdigest()}
        self.assertFalse(GmailDraftAdapter(provider, command['account_scope']).draft(command, gate)['sent'])
        self.assertTrue(gate.finished)
        original['To'] = 'unexpected@example.invalid'
        provider = Gmail(base64.urlsafe_b64encode(original.as_bytes()).decode())
        with self.assertRaises(ReconciliationRequired):
            GmailDraftAdapter(provider, command['account_scope']).draft(command, Gate())

    def test_reconcile_existing_draft_never_writes(self):
        msg = EmailMessage(); msg['Subject'] = 'Synthetic draft'; msg.set_content('No delivery')
        data = msg.as_bytes(); raw = base64.urlsafe_b64encode(data).decode()
        class ResumeGate(Gate):
            def begin(self, command): return {'disposition': 'reconcile', 'draft_id': 'draft-1'}
        provider, gate = Gmail(raw), ResumeGate()
        command = {'command_type': 'draft.create', 'account_scope': 'fixture@example.invalid',
                   'request': {'raw': raw, 'thread_id': 'thread-1'}, 'request_hash': hashlib.sha256(data).hexdigest()}
        GmailDraftAdapter(provider, command['account_scope']).draft(command, gate)
        self.assertTrue(gate.finished); self.assertEqual(provider.writes, 0)

    def test_backlog_requires_positive_no_effect_evidence(self):
        item = {'account_scope': 'fixture@example.invalid', 'thread_id': 't', 'message_id': 'm',
                'legacy_state': 'pending_reprocessing', 'source_reference': 'synthetic:1',
                'source_hash': 'a' * 64, 'effect_state': 'unknown_outcome'}
        self.assertEqual(eligibility(item, set()), 'held_ambiguous_effect')
        item['effect_state'] = 'proven_no_effect'
        item['effect_evidence_verified'] = True
        item['effect_evidence_reference'] = 'synthetic:verified-no-effect'
        self.assertEqual(eligibility(item, set()), 'eligible')
        self.assertEqual(eligibility(item, {('fixture@example.invalid', 't', 'm')}), 'held_duplicate')


if __name__ == '__main__': unittest.main()
