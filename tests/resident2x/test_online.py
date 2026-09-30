import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from ecos.core.contracts import content_hash
from runtime.online2x.executor import Online,semantic_handler

class OnlineTests(unittest.TestCase):
    def test_separate_online_identity_and_postgres_only(self):
        with tempfile.TemporaryDirectory() as directory:
            config={'identity':'ONLINE_ADA_2X','control_plane':'POSTGRESQL','work_sources':['POSTGRESQL'],
                'capabilities':{'ecos.2x.execute':1,'semantic.reasoning':1},'authority':'DOMAIN_SCOPED_PRODUCTION',
                'domain':'synthetic.acceptance','execution_mode':'synthetic','state_directory':directory,'instance_id':'synthetic'}
            runtime=Online(config,Mock(),{})
            self.assertEqual(runtime.stage_kind,'semantic')
            self.assertEqual(runtime.runtime_name,'online-ada-2x')
            for change in ({'identity':'RESIDENT_ADA_2X_HOME01'},{'work_sources':['POSTGRESQL','SHEETS_TASK_LOOP']},{'control_plane':'SHEETS_TASK_LOOP'}):
                with self.assertRaises(ValueError):Online(dict(config,**change),Mock(),{})
    def test_proposal_requires_host_and_governed_submit(self):
        proposal={'id':'proposal','correlation_id':'correlation','items':[]}
        proposal['content_hash']=content_hash(proposal)
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        runtime=SimpleNamespace(root=Path(directory.name),profile={'identity':'ONLINE_ADA_2X'},config={'correlation_id':'correlation'},invoke=Mock(return_value={'data':{'content_hash':proposal['content_hash']}}))
        package={'context_version':1,'stage':{'kind':'semantic'},'fence':{'claim_id':'claim'},'occurrence':{'id':'work'},'source_references':[]}
        interpret=Mock(return_value=proposal);guard=Mock()
        result=semantic_handler(interpret)(runtime,package,guard)
        self.assertFalse(result['provider_business_mutations']);self.assertEqual(guard.call_count,2)
        self.assertEqual(runtime.invoke.call_args.args[0],'semantic.proposal.submit')
        self.assertEqual(runtime.invoke.call_args.args[1]['fence'],package['fence'])
        semantic_handler(interpret)(runtime,package,guard)
        self.assertEqual(interpret.call_count,1)
        runtime.invoke.reset_mock();package['context_version']=2
        with self.assertRaises(ValueError):semantic_handler(interpret)(runtime,package,guard)
        runtime.invoke.assert_not_called()
    def test_no_local_semantic_fallback(self):
        with self.assertRaises(TypeError):semantic_handler(None)

if __name__=='__main__':unittest.main()
