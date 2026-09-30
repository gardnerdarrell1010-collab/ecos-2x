"""Online semantic executor using the accepted PostgreSQL execution lifecycle.

The authenticated Online host supplies semantic interpretation. This module does
not substitute a local model, select a provider, or scan legacy Sheets. A semantic
stage completes only after its proposal is accepted by the governed SQL operation;
business commits and provider effects belong to their separately authorized stages.
"""
import json
from ecos.core.contracts import content_hash
from runtime.resident2x.executor import Resident, save


class Online(Resident):
    expected_identity = 'ONLINE_ADA_2X'
    stage_kind = 'semantic'
    runtime_name = 'online-ada-2x'
    host_name = 'CHATGPT'


def semantic_handler(interpret):
    """Adapt the actual Online host's interpreter; never invent a semantic result."""
    if not callable(interpret):
        raise TypeError('online_interpreter_required')

    def execute(runtime, package, guard):
        if runtime.profile['identity'] != 'ONLINE_ADA_2X':
            raise ValueError('online_identity_required')
        if package['stage']['kind'] != 'semantic':
            raise ValueError('semantic_stage_required')
        guard()
        # The host receives only its current governed package. It must apply the
        # operation allowlist and source versions, which SQL independently checks.
        journal = runtime.root / 'proposals' / (package['occurrence']['id'] + '.json')
        if journal.exists():
            stored = json.loads(journal.read_text(encoding='utf-8'))
            if stored['context_version'] != package['context_version']:
                raise ValueError('semantic_context_changed')
            proposal = stored['proposal']
        else:
            proposal = interpret(package)
        if not isinstance(proposal, dict):
            raise ValueError('semantic_proposal_required')
        if proposal.get('correlation_id') != runtime.config['correlation_id']:
            raise ValueError('proposal_correlation_mismatch')
        digest = content_hash(proposal)
        if proposal.get('content_hash') != digest:
            raise ValueError('proposal_hash_mismatch')
        if not journal.exists():
            save(journal, {'context_version': package['context_version'], 'proposal': proposal})
        guard()
        response = runtime.invoke('semantic.proposal.submit',
            {'fence': package['fence'], 'proposal': proposal},
            key=package['occurrence']['id'] + ':proposal:' + proposal['id'])
        if response.get('data', {}).get('content_hash') != digest:
            raise ValueError('proposal_receipt_mismatch')
        return {'content_hash': digest, 'proposal_id': proposal['id'],
                'source_references': package['source_references'],
                'provider_business_mutations': False}
    return execute
