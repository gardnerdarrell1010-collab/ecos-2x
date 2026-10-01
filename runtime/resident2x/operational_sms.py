"""PostgreSQL bindings around the existing authenticated HTTP and Twilio primitives."""
import base64
import hashlib
import importlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from ecos.core.contracts import content_hash
from runtime.resident2x.capabilities import shared_http


def inline(kind, data):
    return 'data:' + kind + ';base64,' + base64.b64encode(data).decode('ascii')


def text_content(uri, expected):
    prefix = 'data:text/plain;base64,'
    if not uri.startswith(prefix):
        raise ValueError('content_requires_authoritative_resolution')
    raw = base64.b64decode(uri[len(prefix):], validate=True)
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('content_hash_mismatch')
    return raw.decode('utf-8')


def intake(runtime, package, guard, http, parse, account):
    """ACK only after separately committed SQL receipt and body readback."""
    def request(operation, pathname=''):
        guard()
        result = http({'arguments': {'endpoint_id': 'omnichannel_inbound_queue',
            'operation': operation, 'transaction_id': pathname,
            'method': 'POST' if operation == 'queue-ack' else 'GET'}})
        if result.get('error') or result.get('http_status') != 200:
            raise ValueError('queue_transport_failed')
        return result

    listed = request('queue-list')
    if not isinstance(listed.get('items'), list):
        raise ValueError('queue_list_invalid')
    verified, held = [], []
    for entry in listed['items'][:100]:
        pathname = entry.get('pathname') or entry.get('transaction_id') or ''
        if not pathname.startswith('sms-transport/pending/inbound/'):
            continue
        try:
            fetched = request('queue-item', pathname)
            evidence = parse(fetched.get('event', fetched.get('item')), pathname)
            sid = evidence['Provider Message ID']
            rid = str(uuid5(NAMESPACE_URL, 'ecos:twilio:' + account + ':' + sid))
            cid = str(uuid5(NAMESPACE_URL, 'ecos:communication:' + rid))
            raw = json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
            body = evidence['Message Body'].encode()
            stamp = datetime.now(timezone.utc).isoformat()
            receipt = {'id': rid, 'schema_version': '1.0.0', 'created_at': stamp,
                'provider': 'twilio', 'account_scope': account, 'provider_event_id': sid,
                'dedupe_key': sid, 'provider_object_id': sid,
                'provider_occurred_at': evidence['Received/Sent At'], 'received_at': stamp,
                'raw_artifact_uri': inline('application/json', raw),
                'raw_content_hash': hashlib.sha256(raw).hexdigest(),
                # Authentication is supplied by the existing authenticated queue boundary.
                'signature_verified': False, 'correlation_id': str(uuid4())}
            communication = {'id': cid, 'schema_version': '1.0.0', 'created_at': stamp,
                'record_version': 1, 'receipt_id': rid, 'channel': 'sms',
                'provider_thread_id': sid, 'direction': 'inbound', 'sender_party_id': None,
                'body_artifact_uri': inline('text/plain', body),
                'body_hash': hashlib.sha256(body).hexdigest()}
            guard()
            response = runtime.invoke('sms.receipt.persist', {'fence': package['fence'],
                'queue_item': pathname, 'receipt': receipt, 'communication': communication},
                key='sms-receipt:' + package['occurrence']['id'] + ':' + str(uuid4()))['data']
            actual = runtime.read('communication', response['communication']['id'])['record']
            source = runtime.read('provider_receipt', response['receipt']['id'])['record']
            if (actual != response['communication'] or source != response['receipt']
                    or source['raw_content_hash'] != receipt['raw_content_hash']
                    or text_content(actual['body_artifact_uri'], actual['body_hash']) != evidence['Message Body']):
                raise ValueError('receipt_readback_failed')
            ack = request('queue-ack', pathname)
            if ack.get('acknowledged') is not True or ack.get('processed_pathname') != pathname.replace('/pending/', '/processed/', 1):
                raise ValueError('ack_requires_reconciliation')
            verified.append(cid)
        except Exception as exc:
            held.append({'source_hash': hashlib.sha256(pathname.encode()).hexdigest(), 'error_type': type(exc).__name__})
    return {'verified': verified, 'held': held, 'content_hash': content_hash({'verified': verified, 'held': held}),
            'source_references': package['source_references']}


def dispatch(runtime, package, guard, send, configuration):
    """Isolate each delivery. SQL prevents repeating an accepted or ambiguous attempt."""
    after, accepted, held = None, [], []
    while True:
        guard()
        page = runtime.invoke('runtime.scope.read', {'fence': package['fence'],
            'record_type': 'delivery', 'after_id': after, 'limit': 100})['data']
        for row in page['records']:
            delivery = row['record']
            if delivery['channel'] != 'sms' or delivery['state'] not in ('planned', 'ready', 'sending'):
                continue
            try:
                notification = runtime.read('notification', delivery['notification_id'])['record']
                body = text_content(notification['content_artifact_uri'], notification['content_hash'])
                wire = {'to': delivery['destination_reference'], 'from': configuration['sender'], 'body': body}
                guard()
                begin = runtime.invoke('sms.dispatch.begin', {'fence': package['fence'],
                    'delivery_id': delivery['id'], 'expected_version': delivery['record_version'],
                    'account_scope': configuration['account_scope'], 'request': wire})['data']
                if begin['disposition'] == 'completed':
                    accepted.append(delivery['id']); continue
                if begin['disposition'] != 'dispatch':
                    raise ValueError('provider_effect_requires_reconciliation')
                request = {'delivery_id': 'NDEL-' + delivery['id'], 'notification_id': notification['id'],
                    **wire, 'transport': configuration['transport'],
                    'connector_definitions': configuration['connector_definitions']}
                outcome = send(request)
                sid = outcome.provider_message_id
                if not sid:
                    raise ValueError('provider_acceptance_unproven')
                stamp = datetime.now(timezone.utc).isoformat()
                runtime.invoke('provider.result.record', {'result': {'id': str(uuid4()),
                    'schema_version': '1.0.0', 'created_at': stamp,
                    'provider_command_id': begin['command_id'], 'provider_attempt_id': begin['attempt_id'],
                    'outcome': 'reconciled', 'reconciled_outcome': 'succeeded',
                    'observed_at': stamp, 'provider_object_id': sid,
                    'evidence_hash': content_hash(vars(outcome))}}, key='sms-result:' + begin['command_id'])
                guard()
                readback = runtime.invoke('sms.dispatch.readback', {'fence': package['fence'], 'delivery_id': delivery['id']})['data']
                if not readback['provider_acceptance']:
                    raise ValueError('dispatch_readback_failed')
                accepted.append(delivery['id'])
            except Exception as exc:
                held.append({'delivery_id': delivery['id'], 'error_type': type(exc).__name__})
        if len(page['records']) < 100:
            break
        after = page['last_scanned_id']
    return {'accepted': accepted, 'held': held, 'content_hash': content_hash({'accepted': accepted, 'held': held}),
            'source_references': package['source_references']}


def make_handlers(config):
    configuration = config['operational_sms']
    http_class = shared_http(config)
    parser = importlib.import_module('ecos_runtime.communications').inbound_evidence
    sms = importlib.import_module('ecos_capability.sms')
    root = Path(config['shared_capability']['root']).resolve()
    if Path(sms.__file__).resolve() != root / 'ecos_capability/sms.py':
        raise ValueError('sms_primitive_origin_mismatch')
    node_root = root.parents[3]
    sms.ROOT = node_root
    node = json.loads((node_root / 'config/node.json').read_text(encoding='utf-8-sig'))
    google_reference = Path(node['google_service_account'])
    providers = importlib.import_module('ecos_runtime.provider_tools')
    if Path(providers.__file__).resolve() != root / 'ecos_runtime/provider_tools.py':
        raise ValueError('credential_resolver_origin_mismatch')
    tools = providers.GovernedProviderTools(google_reference, lambda: {},
        connector_definitions=configuration['connector_definitions'],
        credential_base_references={'ECOS_NODE_GOOGLE_SERVICE_ACCOUNT_REFERENCE': google_reference})
    def resolve(reference, resource, **kwargs):
        return tools._secure_http_credential(reference, resource, **kwargs)
    http = http_class(configuration['http_transports'], resolve)
    return {
        'sms_transport_queue_consume': lambda runtime, package, guard: intake(runtime, package, guard, http, parser, configuration['account_scope']),
        'sms_outbound_dispatch': lambda runtime, package, guard: dispatch(runtime, package, guard, sms.send_sms, configuration),
    }
