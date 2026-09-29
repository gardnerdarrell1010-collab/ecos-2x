from typing import Protocol


class GovernedOperations(Protocol):
    def invoke(self, operation: str, request: dict) -> dict: ...


class SemanticExecutor(Protocol):
    """Return immutable schema-bound proposal; never table SQL or credentials."""
    def propose(self, bootstrap_package: dict, work_package: dict) -> dict: ...
