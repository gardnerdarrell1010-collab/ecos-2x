"""Conservative eligibility decision for already-read legacy Gmail evidence."""
import re


def eligibility(item, known_identities):
    key = (item.get('account_scope'), item.get('thread_id'), item.get('message_id'))
    if not all(isinstance(value, str) and value.strip() for value in key):
        return 'held_missing_provider_identity'
    if key in known_identities:
        return 'held_duplicate'
    if item.get('effect_state') in ('completed', 'succeeded', 'sent', 'reconciled_success'):
        return 'held_completed_effect'
    if (item.get('effect_state') != 'proven_no_effect'
            or item.get('effect_evidence_verified') is not True
            or not item.get('effect_evidence_reference')):
        return 'held_ambiguous_effect'
    if item.get('legacy_state') not in ('pending_validation', 'pending_reprocessing'):
        return 'held_not_pending'
    if not item.get('source_reference') or not re.fullmatch(r'[a-f0-9]{64}', item.get('source_hash', '')):
        return 'held_missing_provenance'
    return 'eligible'
