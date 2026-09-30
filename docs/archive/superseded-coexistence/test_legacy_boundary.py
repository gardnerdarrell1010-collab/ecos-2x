import importlib.util,sys,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,MagicMock,patch
HERE=Path(__file__).parent
sys.dont_write_bytecode=True
sys.path.insert(0,'D:/ECOS/Node/runtime/releases/slots/1.0.011')
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
load('ecos_runtime.domain_effects',Path('C:/ECOS/ecos-2x/runtime/domain_effects.py'))
adapter=load('ecos_runtime.domain_authority',HERE/'domain_authority.py')
class BoundaryTests(unittest.TestCase):
 def test_real_dispatch_resolver_guards_only_wave1(self):
  module=load('ecos_runtime.authority_dispatch_candidate',HERE/'resident_governed.py')
  dispatcher=object.__new__(module.ResidentGovernedDispatcher);dispatcher.capabilities=set()
  for task,stage in [('TASK-AUTO-000029','toast-refresh'),('TASK-AUTO-000047','dashboard-source-c'),('TASK-AUTO-000029-B','staffing-historical-summary')]:
   dispatcher._deterministic_stage=Mock(return_value=(stage,[]))
   item=SimpleNamespace(task_id=task)
   _,_,worker=dispatcher._deterministic_stage_executor(item)
   import importlib
   original=importlib.import_module('ecos_runtime.'+stage.replace('-','_')+'_worker').execute
   if task.endswith('-B'):
    self.assertIs(worker,original)
   else:
    with patch.object(adapter,'execute',return_value='guarded') as guard:
     # The dispatcher resolves the guard when binding the callable.
     _,_,worker=dispatcher._deterministic_stage_executor(item)
     self.assertEqual(worker(dispatcher,{},item,'run'),'guarded')
     guard.assert_called_once_with(dispatcher,{},item,'run',original)
 def fixture(self):
  db=MagicMock();db.__enter__.return_value=db
  db.execute.return_value.fetchone.return_value=({'command_id':'synthetic','already_completed':False},)
  client=adapter.DomainEffects(Mock(return_value=db))
  dispatcher=Mock();dispatcher._occurrence_id.return_value='occurrence'
  item=SimpleNamespace(task_id='TASK-AUTO-000029',payload={'Instructions':'synthetic'})
  grant={'target':'toast.compatibility','epoch':1}
  return db,client,dispatcher,item,grant
 def test_current_grant_preserves_worker_result(self):
  db,c,d,i,g=self.fixture();outcome={'verification_result':'PASSED'};worker=Mock(return_value=outcome)
  with patch.object(adapter,'capture',return_value=(c,g)),patch.object(adapter,'_readback',return_value={'verified':True}):
   self.assertIs(adapter.execute(d,{},i,'run',worker),outcome)
  worker.assert_called_once_with(d,{},i,'run');self.assertEqual(db.execute.call_count,2)
 def test_stale_epoch_prevents_all_worker_provider_calls(self):
  for task,target in [('TASK-AUTO-000029','toast.compatibility'),('TASK-AUTO-000047','toast.dashboard')]:
   db,c,d,i,g=self.fixture();i.task_id=task;g['target']=target;db.execute.side_effect=PermissionError('stale_authority_epoch');worker=Mock()
   with patch.object(adapter,'capture',return_value=(c,g)),self.assertRaises(PermissionError):adapter.execute(d,{},i,'run',worker)
   worker.assert_not_called()
 def test_worker_failure_retains_unresolved_effect(self):
  db,c,d,i,g=self.fixture();worker=Mock(side_effect=RuntimeError('ambiguous provider'))
  with patch.object(adapter,'capture',return_value=(c,g)),self.assertRaises(RuntimeError):adapter.execute(d,{},i,'run',worker)
  self.assertEqual(db.execute.call_count,1)
 def test_readback_failure_prevents_reconciliation(self):
  db,c,d,i,g=self.fixture()
  with patch.object(adapter,'capture',return_value=(c,g)),patch.object(adapter,'_readback',side_effect=ValueError('mismatch')),self.assertRaises(ValueError):adapter.execute(d,{},i,'run',Mock(return_value={}))
  self.assertEqual(db.execute.call_count,1)
 def test_completed_replay_never_repeats_provider(self):
  db,c,d,i,g=self.fixture();db.execute.return_value.fetchone.return_value=({'command_id':'synthetic','already_completed':True},);worker=Mock()
  with patch.object(adapter,'capture',return_value=(c,g)),self.assertRaisesRegex(ValueError,'outcome_reconciliation'):adapter.execute(d,{},i,'run',worker)
  worker.assert_not_called()
if __name__=='__main__':unittest.main()
