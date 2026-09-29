from typing import Protocol


class ProviderAdapter(Protocol):
    """Phase 1+ adapters must persist intent before send and evidence after send.

    Implementations receive scoped secret references outside database transactions.
    Every send is preceded by current authorization, fence, approval and policy checks.
    """
    def dispatch(self, command: dict) -> dict: ...
    def reconcile(self, command: dict) -> dict: ...
    def normalize_receipt(self, receipt: dict) -> dict: ...
