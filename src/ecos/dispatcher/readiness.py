from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Candidate:
    occurrence_id: str
    created_at: datetime
    due_at: datetime
    required_capabilities: frozenset[str] = frozenset()
    enabled: bool = True
    terminal: bool = False
    dependencies_satisfied: bool = True
    approvals_satisfied: bool = True
    maintenance: bool = False
    idempotency_safe: bool = True
    safety_gates_satisfied: bool = True
    live_claim: bool = False
    retry_at: datetime | None = None
    ready_override_at: datetime | None = None
    priority_override: int = 0
    priority_override_expires_at: datetime | None = None
    sla_deadline: datetime | None = None
    deadline: datetime | None = None
    business_impact: int = 0
    recurrence_period_seconds: int | None = None


def selection(candidate: Candidate, capabilities: frozenset[str], now: datetime):
    c = candidate
    if now.tzinfo is None or any(t is not None and t.tzinfo is None for t in
        (c.created_at, c.due_at, c.retry_at, c.ready_override_at, c.priority_override_expires_at, c.sla_deadline, c.deadline)):
        raise ValueError("Timezone-aware instants required")
    if not -100 <= c.priority_override <= 100 or not 0 <= c.business_impact <= 100:
        raise ValueError("Priority inputs outside contract bounds")
    if c.recurrence_period_seconds is not None and c.recurrence_period_seconds <= 0:
        raise ValueError("Recurrence denominator must be positive")
    immediate = c.ready_override_at is not None and c.ready_override_at <= now
    gates = {
        "disabled": c.enabled, "terminal": not c.terminal,
        "not_due": c.due_at <= now or immediate,
        "retry_backoff": c.retry_at is None or c.retry_at <= now,
        "dependency": c.dependencies_satisfied, "approval": c.approvals_satisfied,
        "capability": c.required_capabilities <= capabilities,
        "maintenance": not c.maintenance, "idempotency": c.idempotency_safe,
        "safety": c.safety_gates_satisfied, "live_claim": not c.live_claim,
    }
    reasons = sorted(key for key, allowed in gates.items() if not allowed)
    override = c.priority_override if c.priority_override_expires_at is not None and c.priority_override_expires_at > now else 0
    sla = max(0, int((now - c.sla_deadline).total_seconds())) if c.sla_deadline else 0
    # Fixed one-day pressure window is a versioned initial ordering convention, not an optimized weighting formula.
    pressure = max(0, 86400 - int((c.deadline - now).total_seconds())) if c.deadline else 0
    age = max(0, int((now - c.due_at).total_seconds()))
    relative = age * 10000 // (c.recurrence_period_seconds or 86400)
    # Python ascending tuple corresponds to SQL descending priority terms + ascending stable ties.
    key = (-override, -int(immediate), -sla, -pressure, -c.business_impact, -relative, c.created_at, c.occurrence_id)
    evidence = {"policy_version": "lexicographic-v1", "evaluated_at": now.isoformat(), "source_versions": [],
        "eligible": not reasons, "reason_codes": reasons, "priority_override": override,
        "immediate_ready": immediate, "sla_breach_seconds": sla, "deadline_pressure_seconds": pressure,
        "business_impact": c.business_impact, "recurrence_relative_age_basis_points": relative,
        "created_at": c.created_at.isoformat(), "occurrence_id": c.occurrence_id}
    return not reasons, key, evidence
