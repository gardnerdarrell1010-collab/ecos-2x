/** Transport-only policy. PostgreSQL remains the operation authorization authority. */
export const OPERATIONS = Object.freeze([
  'executor.register', 'executor.heartbeat', 'work.next', 'work.package',
  'work.claim', 'work.renew', 'work.complete', 'work.fail', 'work.defer',
  'work.release', 'semantic.proposal.submit', 'fact.record',
  'task.evidence.attach', 'provider.result.record',
]);

export function boundRequest(operation, request, identity) {
  if (!OPERATIONS.includes(operation)) throw new Error('operation_not_allowed');
  if (!request || typeof request !== 'object' || Array.isArray(request)) throw new Error('invalid_request');
  const context = request.context;
  if (!context || context.principal_id !== identity.principal ||
      context.executor_instance_id !== identity.instance) throw new Error('identity_mismatch');
  if (request.schema_version !== '1.0.0') throw new Error('unsupported_schema');
  if (JSON.stringify(request).length > 262144) throw new Error('request_too_large');
  // No SQL, role selection, operation substitution, or identity comes from headers.
  return structuredClone(request);
}

export function authorizedClaims(claims, identity) {
  return claims.sub === identity.subject && claims.client_id === identity.client &&
    claims.role === 'authenticated' && typeof claims.exp === 'number';
}

export function databaseLoginAllowed(url) {
  const parsed = new URL(url);
  return ['postgres:', 'postgresql:'].includes(parsed.protocol) &&
    /^online2x_[a-z0-9_]+(?:\.[a-z0-9]+)?$/.test(decodeURIComponent(parsed.username));
}
