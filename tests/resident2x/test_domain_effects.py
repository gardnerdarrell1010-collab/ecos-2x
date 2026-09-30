import unittest
from unittest.mock import Mock, MagicMock
from runtime.domain_effects import DomainEffects


class DomainEffectBoundaryTests(unittest.TestCase):
    def setup_effect(self):
        connect=Mock(); db=MagicMock();connect.return_value=db;db.__enter__.return_value=db
        db.execute.return_value.fetchone.return_value=({'command_id':'synthetic-command','already_completed':False},)
        return DomainEffects(connect),db
    def test_stale_epoch_rejects_before_drive_or_registry_callback(self):
        for target in ('toast.compatibility','toast.dashboard'):
            client,db=self.setup_effect(); db.execute.side_effect=PermissionError('stale_authority_epoch')
            mutation=Mock();verify=Mock()
            with self.subTest(target=target),self.assertRaises(PermissionError):
                client.execute({'target':target,'epoch':1},'synthetic-run','a'*64,mutation,verify)
            mutation.assert_not_called();verify.assert_not_called()
    def test_ambiguous_reservation_commit_never_calls_provider(self):
        client,db=self.setup_effect();db.__exit__.side_effect=ConnectionError('unknown commit')
        mutation=Mock()
        with self.assertRaises(ConnectionError):
            client.execute({'target':'toast.compatibility','epoch':1},'run','a'*64,mutation,Mock())
        mutation.assert_not_called()
    def test_provider_failure_preserves_unresolved_reservation(self):
        client,db=self.setup_effect();mutation=Mock(side_effect=ConnectionError('ambiguous provider'))
        with self.assertRaises(ConnectionError):
            client.execute({'target':'toast.compatibility','epoch':1},'run','a'*64,mutation,Mock())
        self.assertEqual(db.execute.call_count,1)
    def test_independent_verification_required_before_finish(self):
        client,db=self.setup_effect()
        with self.assertRaisesRegex(ValueError,'readback'):
            client.execute({'target':'toast.compatibility','epoch':1},'run','a'*64,Mock(),lambda:{'verified':False})
        self.assertEqual(db.execute.call_count,1)
    def test_committed_replay_never_repeats_provider_mutation(self):
        client,db=self.setup_effect()
        db.execute.return_value.fetchone.return_value=({'command_id':'synthetic-command','already_completed':True},)
        mutation=Mock()
        client.execute({'target':'toast.compatibility','epoch':1},'run','a'*64,mutation,lambda:{'verified':True,'sha256':'b'*64})
        mutation.assert_not_called()
        self.assertEqual(db.execute.call_count,2)
