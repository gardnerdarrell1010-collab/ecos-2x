"""Durable provider-effect barrier on the existing SQL authority/epoch.

Connection failure never clears an unresolved provider attempt. Transfer must
wait for reconciliation rather than allowing an in-flight old provider request
to finish after a new generation takes authority.
"""
import hashlib
import json


class DomainEffects:
    def __init__(self, connect):
        self.connect = connect

    def capture(self, target):
        # Capture once at execution start; never refresh a stale grant at commit.
        with self.connect() as db:
            return db.execute('select ecos.domain_effect_grant(%s)', (target,)).fetchone()[0]

    def execute(self, grant, execution_key, request_hash, effect, verify):
        with self.connect() as db:
            reservation = db.execute('select ecos.domain_effect_begin(%s,%s,%s,%s)',
                (grant['target'], grant['epoch'], execution_key, request_hash)).fetchone()[0]
        # This transaction MUST have committed before any external call.
        # An ambiguous commit raises; never execute from an unconfirmed response.
        if not reservation['already_completed']:
            effect()
        evidence = verify()  # independent exact provider/registry readback
        if not isinstance(evidence, dict) or evidence.get('verified') is not True:
            raise ValueError('domain_effect_readback_required')
        digest = hashlib.sha256(json.dumps(evidence, sort_keys=True,
            separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
        with self.connect() as db:
            db.execute('select ecos.domain_effect_finish(%s,%s,%s)',
                (reservation['command_id'], grant['epoch'], digest))
        return evidence
