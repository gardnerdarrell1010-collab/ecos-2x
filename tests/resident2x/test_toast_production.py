"""Exercise production acquisition through the same fenced commit and readback."""
import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from runtime.resident2x import toast_wave1 as m

class ToastProductionTests(unittest.TestCase):
    def run_case(self,corrupt=False,effects=False):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'toast').mkdir()
            data={'restaurant_hash':'a'*64,'business_date':'2026-09-27','observation_json':'{}','projection_json':'{}','source_hash':'b'*64}
            (root/'toast/work.json').write_text(json.dumps(data))
            committed=dict(data,id='batch',content_hash='c'*64)
            if corrupt:committed['source_hash']='d'*64
            db=Mock();db.execute.return_value.fetchone.side_effect=[(None,),(committed,)]
            connection=Mock();connection.__enter__=Mock(return_value=db);connection.__exit__=Mock(return_value=False)
            runtime=SimpleNamespace(root=root,connect=Mock(return_value=connection),invoke=Mock(return_value={'data':{'content_hash':'c'*64}}),read=Mock(return_value={}),reference=Mock(return_value={'record_type':'task'}))
            config={'domain':'toast.acquisition','execution_mode':'production','provider_effects_enabled':effects,'wave1':{'shared_root':'synthetic'}}
            package={'occurrence':{'id':'work'},'input':{},'fence':{'claim_id':'claim'},'task':{'id':'task'}}
            with patch.object(m,'modules',return_value=(Mock(),Mock(),Mock())):
                operation=m.handler(config)
                if corrupt or effects:
                    with self.assertRaises(ValueError):operation(runtime,package,Mock())
                    if effects:runtime.invoke.assert_not_called()
                else:
                    result=operation(runtime,package,Mock())
                    self.assertTrue(result['sql_readback_verified']);self.assertFalse(result['provider_business_mutations'])
                    self.assertEqual(runtime.invoke.call_args.args[0],'toast.batch.commit')
                    self.assertEqual(runtime.invoke.call_args.args[1]['fence'],package['fence'])
                    self.assertEqual(db.execute.call_args_list[-1].args,('select ecos.toast_readback(%s)',('work',)))
    def test_production_reuses_fenced_commit_and_independent_readback(self):self.run_case()
    def test_wrong_committed_source_rejected(self):self.run_case(corrupt=True)
    def test_provider_write_configuration_rejected(self):self.run_case(effects=True)

if __name__=='__main__':unittest.main()
