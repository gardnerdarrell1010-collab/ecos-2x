import unittest
from types import SimpleNamespace
from unittest.mock import patch
from runtime.resident2x.executor import Resident, OperationRejected

class GmailGateResumeTest(unittest.TestCase):
    def check(self, domain, second_error=None):
        calls=[]
        runtime=object.__new__(Resident)
        runtime.config={'domain':domain,'lease_seconds':120}
        runtime.connect=lambda:None
        runtime.stopping=SimpleNamespace(is_set=lambda:False)
        runtime.heartbeat=lambda *args:None
        def invoke(operation, arguments, **kwargs):
            calls.append(operation)
            if len(calls)==1: raise OperationRejected('work.renew','gate_blocked')
            if second_error: raise OperationRejected('work.renew',second_error)
        runtime.invoke=invoke
        class ImmediateThread:
            def __init__(self,target,**kwargs):self.target=target
            def start(self):self.target()
            def join(self,**kwargs):pass
        event=SimpleNamespace(wait=lambda _:False,set=lambda:None)
        client=SimpleNamespace(close=lambda:None)
        with patch('runtime.resident2x.executor.threading.Thread',ImmediateThread), patch('runtime.resident2x.executor.threading.Event',return_value=event), patch('runtime.resident2x.executor.GovernedClient',return_value=client):
            with runtime.keepalive({'claim_id':'synthetic'}) as guard:guard()
        return calls
    def test_gmail_requires_successful_fresh_renewal(self):
        self.assertEqual(self.check('gmail.operations'),['work.renew']*3)
    def test_expired_fence_stays_rejected(self):
        with self.assertRaises(OperationRejected) as result:self.check('gmail.operations','expired_fence')
        self.assertEqual(result.exception.code,'expired_fence')
    def test_toast_behavior_unchanged(self):
        with self.assertRaises(OperationRejected) as result:self.check('toast.acquisition')
        self.assertEqual(result.exception.code,'gate_blocked')

if __name__=='__main__':unittest.main()
