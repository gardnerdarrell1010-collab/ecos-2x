from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest

from ecos.adapters.provider_policy import next_action
from ecos.core.proposals import classify_items
from ecos.dispatcher.readiness import Candidate, selection
from tests.fixtures import proposal, rehash, uid


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026,9,28,12,tzinfo=timezone.utc)
        self.base = Candidate(uid(), self.now-timedelta(days=2), self.now-timedelta(hours=1))

    def test_run_now_cannot_bypass_any_gate(self):
        urgent = replace(self.base, due_at=self.now+timedelta(days=3), ready_override_at=self.now,
                         priority_override=100, priority_override_expires_at=self.now+timedelta(hours=1))
        self.assertTrue(selection(urgent, frozenset(), self.now)[0])
        gates = [{"dependencies_satisfied":False},{"approvals_satisfied":False},{"maintenance":True},
                 {"idempotency_safe":False},{"safety_gates_satisfied":False},{"live_claim":True},
                 {"required_capabilities":frozenset({"semantic.interpret"})},{"enabled":False},
                 {"terminal":True},{"retry_at":self.now+timedelta(seconds=10)}]
        for gate in gates:
            with self.subTest(gate=gate):
                eligible, _, evidence = selection(replace(urgent, **gate), frozenset(), self.now)
                self.assertFalse(eligible)
                self.assertTrue(evidence["reason_codes"])

    def test_capability_mismatch_is_pair_local(self):
        candidate = replace(self.base, required_capabilities=frozenset({"provider.toast"}))
        self.assertFalse(selection(candidate,frozenset({"semantic.interpret"}),self.now)[0])
        self.assertTrue(selection(candidate,frozenset({"provider.toast"}),self.now)[0])
        self.assertTrue(selection(self.base,frozenset({"semantic.interpret"}),self.now)[0])

    def test_priority_override_does_not_make_future_work_due(self):
        candidate = replace(self.base,due_at=self.now+timedelta(days=1),priority_override=100,
                            priority_override_expires_at=self.now+timedelta(hours=1))
        self.assertFalse(selection(candidate,frozenset(),self.now)[0])

    def test_expiry_and_stable_ordering(self):
        expired = replace(self.base,priority_override=100,priority_override_expires_at=self.now)
        self.assertEqual(selection(self.base,frozenset(),self.now)[1],selection(expired,frozenset(),self.now)[1])
        second = replace(self.base,occurrence_id=uid(2))
        self.assertLess(selection(self.base,frozenset(),self.now)[1],selection(second,frozenset(),self.now)[1])
        self.assertEqual(selection(self.base,frozenset(),self.now),selection(self.base,frozenset(),self.now))

    def test_recurrence_age_explained_and_invalid_inputs_rejected(self):
        hourly = replace(self.base,recurrence_period_seconds=3600)
        daily = replace(self.base,recurrence_period_seconds=86400)
        self.assertGreater(selection(hourly,frozenset(),self.now)[2]["recurrence_relative_age_basis_points"],
                           selection(daily,frozenset(),self.now)[2]["recurrence_relative_age_basis_points"])
        for bad in (replace(self.base,recurrence_period_seconds=0), replace(self.base,priority_override=101),
                    replace(self.base,due_at=datetime(2026,9,28))):
            with self.assertRaises(ValueError):
                selection(bad,frozenset(),self.now)


class ProposalTests(unittest.TestCase):
    def setUp(self):
        self.value = proposal()
        self.current = {("task",uid(1)):1,("task",uid(2)):1}

    def test_stale_sibling_isolated(self):
        self.current[("task",uid(1))] = 2
        self.assertEqual(classify_items(self.value,self.current,{}),{uid(101):"stale",uid(102):"valid"})

    def test_restart_reuses_committed_item_even_after_source_changed(self):
        self.current[("task",uid(1))] = 2
        committed = {(self.value["id"],uid(101)):self.value["content_hash"]}
        self.assertEqual(classify_items(self.value,self.current,committed)[uid(101)],"committed")
        committed[(self.value["id"],uid(101))] = "f"*64
        with self.assertRaises(ValueError):
            classify_items(self.value,self.current,committed)

    def test_invalid_conflicting_ambiguous_evidence_and_dependency(self):
        for flag,expected in [("unverified","invalid"),("conflicting","conflicting")]:
            value = proposal()
            value["items"][0]["evidence"][0]["verification"] = flag
            value["items"][1]["depends_on_item_ids"] = [uid(101)]
            result = classify_items(rehash(value),self.current,{})
            self.assertEqual(result,{uid(101):expected,uid(102):"blocked"})
        value = proposal()
        value["items"][0]["unresolved_ambiguity"] = ["unknown owner"]
        self.assertEqual(classify_items(rehash(value),self.current,{})[uid(101)],"ambiguous")

    def test_hash_cycle_duplicate_and_missing_dependency_rejected(self):
        value = proposal()
        value["items"][0]["unresolved_ambiguity"] = ["tampered"]
        with self.assertRaises(ValueError):
            classify_items(value,self.current,{})
        for mode in ("cycle","duplicate","missing"):
            value = proposal()
            if mode == "cycle":
                value["items"][0]["depends_on_item_ids"] = [uid(102)]
                value["items"][1]["depends_on_item_ids"] = [uid(101)]
            elif mode == "duplicate":
                value["items"][1]["item_id"] = uid(101)
            else:
                value["items"][0]["depends_on_item_ids"] = [uid(999)]
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                classify_items(rehash(value),self.current,{})

    def test_expected_versions_cover_operation_and_summary(self):
        value = proposal()
        value["items"][0]["proposed_operations"][0]["arguments"]["expected_version"] = 2
        self.assertEqual(classify_items(rehash(value),self.current,{})[uid(101)],"invalid")
        value = proposal()
        value["expected_record_versions"].pop()
        with self.assertRaises(ValueError):
            classify_items(rehash(value),self.current,{})


class ProviderPolicyTests(unittest.TestCase):
    def test_reconciliation_does_not_mean_success_or_safe_retry(self):
        with self.assertRaises(ValueError):
            next_action("reconciled")
        self.assertEqual(next_action("reconciled",reconciled_outcome="succeeded"),"stop")
        self.assertEqual(next_action("reconciled",reconciled_outcome="no_effect",retryable=True),"retry_same_command")
        self.assertEqual(next_action("reconciled",reconciled_outcome="failed",retryable=True),"reconcile")

    def test_unknown_and_accepted_never_blindly_send(self):
        for outcome in ("unknown_outcome","accepted"):
            self.assertEqual(next_action(outcome,native_idempotency=True,native_key_still_valid=True,retryable=True),"reconcile")

    def test_success_stops_and_failure_needs_evidence(self):
        self.assertEqual(next_action("succeeded"),"stop")
        self.assertEqual(next_action("failed",retryable=True),"reconcile")
        self.assertEqual(next_action("failed",retryable=True,proof_no_effect=True),"retry_same_command")
        self.assertEqual(next_action("failed",retryable=True,native_idempotency=True),"reconcile")
        self.assertEqual(next_action("failed",retryable=True,proof_no_effect=True,attempts_remaining=False),"dead_letter")
        self.assertEqual(next_action("failed",retryable=False),"dead_letter")
        with self.assertRaises(ValueError):
            next_action("sent_probably")
