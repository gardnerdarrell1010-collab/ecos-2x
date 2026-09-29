"""Executable Phase 1 PostgreSQL acceptance logic; no implementation/connection supplied."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from typing import Protocol


class FenceRejected(Exception):
    """Future driver maps expired/stale DB errors to this exception."""


class PostgreSQLClaimDriver(Protocol):
    """Use 100 independent database sessions against an explicitly disposable target.

    Each method must have bounded DB statement/connection timeouts. Test-only expiry uses
    fixture controls in that target, never changes the server clock or production state.
    """
    fixture_scope: str
    def prepare_one_occurrence(self) -> str: ...
    def claim(self, occurrence_id: str, contender: int) -> dict | None: ...
    def live_claims(self, occurrence_id: str) -> list[dict]: ...
    def execution_runs(self, occurrence_id: str) -> list[dict]: ...
    def stage_evidence(self, occurrence_id: str) -> dict: ...
    def expire_for_test(self, claim: dict) -> None: ...
    def recover(self, occurrence_id: str) -> None: ...
    def renew(self, claim: dict) -> None: ...
    def complete(self, claim: dict) -> None: ...


def assert_claim_observations(results, live_claims, runs):
    if len(results) != 100:
        raise AssertionError("Exactly 100 contender results required")
    winners = [result for result in results if result is not None]
    if len(winners) != 1 or len(live_claims) != 1 or len(runs) != 1:
        raise AssertionError("100 contenders must produce exactly one valid claim and one run")
    winner = winners[0]
    for field in ("claim_id","occurrence_id","stage_definition_id","claim_version","fence_token","executor_instance_id"):
        if not winner.get(field) or live_claims[0][field] != winner[field] or runs[0][field] != winner[field]:
            raise AssertionError("Claim/run/fence ownership mismatch: " + field)
    if live_claims[0]["expired"] or live_claims[0]["state"] != "active":
        raise AssertionError("Winner must own an unexpired active claim")
    return winner


def assert_hundred_contenders(driver: PostgreSQLClaimDriver):
    if driver.fixture_scope != "synthetic_disposable_postgresql":
        raise ValueError("Driver target is not an authorized disposable PostgreSQL fixture")
    occurrence = driver.prepare_one_occurrence()
    barrier = Barrier(100, timeout=30)
    def contend(number):
        barrier.wait()
        return driver.claim(occurrence,number)
    with ThreadPoolExecutor(max_workers=100) as pool:
        futures = [pool.submit(contend,n) for n in range(100)]
        results = [future.result(timeout=45) for future in futures]
    return assert_claim_observations(results,driver.live_claims(occurrence),driver.execution_runs(occurrence))


def assert_lease_recovery(driver: PostgreSQLClaimDriver):
    if driver.fixture_scope != "synthetic_disposable_postgresql":
        raise ValueError("Unsafe fixture scope")
    occurrence = driver.prepare_one_occurrence()
    old = driver.claim(occurrence,0)
    if old is None:
        raise AssertionError("Initial owner absent")
    evidence = driver.stage_evidence(occurrence)
    driver.expire_for_test(old)
    for action in (driver.renew,driver.complete):
        try:
            action(old)
        except FenceRejected:
            pass
        else:
            raise AssertionError("Expired fence was accepted")
    driver.recover(occurrence)
    replacement = driver.claim(occurrence,1)
    if replacement is None or replacement["claim_version"] <= old["claim_version"] or replacement["fence_token"] == old["fence_token"]:
        raise AssertionError("Recovery must create a new monotonic owner/fence")
    if driver.stage_evidence(occurrence) != evidence:
        raise AssertionError("Lease recovery erased completed-stage evidence")
    live = driver.live_claims(occurrence)
    if len(live) != 1 or live[0]["claim_id"] != replacement["claim_id"]:
        raise AssertionError("Recovery did not establish one owner")
    try:
        driver.complete(old)
    except FenceRejected:
        pass
    else:
        raise AssertionError("Stale owner completed after replacement")
