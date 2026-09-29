import unittest

from tests.concurrency.acceptance import assert_claim_observations
from tests.fixtures import uid


class ClaimOracleTests(unittest.TestCase):
    """Test the acceptance assertions, not database concurrency itself."""
    def setUp(self):
        self.claim = {"claim_id":uid(),"occurrence_id":uid(2),"stage_definition_id":uid(3),
            "claim_version":1,"fence_token":uid(4),"executor_instance_id":uid(5),
            "expired":False,"state":"active"}
        self.results = [self.claim]+[None]*99

    def test_complete_single_owner_observations_pass_oracle(self):
        self.assertEqual(assert_claim_observations(self.results,[self.claim],[self.claim]),self.claim)

    def test_double_winner_missing_run_stale_fence_and_wrong_sample_fail(self):
        bad = [(self.results[:-1],[self.claim],[self.claim]),
               ([self.claim,self.claim]+[None]*98,[self.claim],[self.claim]),
               (self.results,[self.claim],[]),
               (self.results,[self.claim|{"expired":True}],[self.claim]),
               (self.results,[self.claim],[self.claim|{"executor_instance_id":uid(99)}])]
        for results,claims,runs in bad:
            with self.subTest(rows=len(results)), self.assertRaises(AssertionError):
                assert_claim_observations(results,claims,runs)
