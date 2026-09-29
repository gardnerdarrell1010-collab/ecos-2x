def next_action(outcome, *, proof_no_effect=False, native_idempotency=False,
                native_key_still_valid=False, retryable=False, attempts_remaining=True,
                reconciled_outcome=None):
    """Unknown success windows always require reconciliation before dispatch."""
    if outcome == "succeeded":
        return "stop"
    if outcome == "reconciled":
        if reconciled_outcome == "succeeded":
            return "stop"
        if reconciled_outcome not in {"failed", "no_effect"}:
            raise ValueError("Reconciled outcome requires explicit verified resolution")
        return next_action("failed", proof_no_effect=reconciled_outcome == "no_effect",
            native_idempotency=native_idempotency, native_key_still_valid=native_key_still_valid,
            retryable=retryable, attempts_remaining=attempts_remaining)
    if outcome in {"unknown_outcome", "accepted"}:
        return "reconcile"
    if outcome == "pending":
        return "dispatch"
    if outcome != "failed":
        raise ValueError("Unknown provider outcome")
    if not retryable or not attempts_remaining:
        return "dead_letter"
    if proof_no_effect or (native_idempotency and native_key_still_valid):
        return "retry_same_command"
    return "reconcile"
