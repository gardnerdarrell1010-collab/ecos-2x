# Fixture policy

Phase 0 executable synthetic payloads are in `contract-examples.json`, generated from
`tests/fixtures.py` by `scripts/build_fixtures.py`; no production
extract is present. Phase 1 database fixtures must instantiate the same IDs, disconnected
providers and assertions on an explicitly designated disposable test database. Include
one independent task with null project, staged semantic/provider work, 100 contenders,
expired fence, ambiguous send, duplicate receipt, conflicted sibling and memory head.
No test fixture may seed live addresses, credentials, provider objects or production IDs.
