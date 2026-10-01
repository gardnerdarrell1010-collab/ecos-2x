// Portable encryption/parity adapter; database operations remain authoritative.
export const canonical = v => Array.isArray(v) ? '['+v.map(canonical).join(',')+']' :
  v !== null && typeof v === 'object' ? '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}' : JSON.stringify(v);
export const decode = s => Uint8Array.from(atob(s),c=>c.charCodeAt(0));
export const encode = bytes => {
  let s='';for(let i=0;i<bytes.length;i+=8192)s+=String.fromCharCode(...bytes.subarray(i,i+8192));return btoa(s);
};
export const digest = async bytes => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))).map(x=>x.toString(16).padStart(2,'0')).join('');
export async function encryptSnapshot(records,boundary,keyBytes,requestId) {
  if(keyBytes.length!==32)throw new Error('continuity_key_unavailable');
  const key=await crypto.subtle.importKey('raw',keyBytes,'AES-GCM',false,['encrypt','decrypt']);
  if(!requestId)throw new Error('continuity_request_id_required');
  // Retries reuse the immutable SQL snapshot and exact ciphertext. HMAC derives
  // a request-specific nonce without storing another runtime checkpoint.
  const nonceKey=await crypto.subtle.importKey('raw',keyBytes,{name:'HMAC',hash:'SHA-256'},false,['sign']);
  const iv=new Uint8Array(await crypto.subtle.sign('HMAC',nonceKey,
    new TextEncoder().encode('ecos-continuity-nonce:'+requestId+':'+canonical(boundary)))).slice(0,12);
  const plaintext=new TextEncoder().encode(canonical(records));
  const aad=new TextEncoder().encode(canonical(boundary));
  const compressed=new Uint8Array(await new Response(new Blob([plaintext]).stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer());
  const ciphertext=new Uint8Array(await crypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:aad},key,compressed));
  const wire={ciphertext:encode(ciphertext),ciphertext_sha256:await digest(ciphertext),
    verified_plaintext_sha256:await digest(plaintext),iv:encode(iv)};
  await verifySnapshot(wire,boundary,keyBytes);
  return wire;
}
export async function verifySnapshot(wire,boundary,keyBytes) {
  const bytes=decode(wire.ciphertext);
  if(await digest(bytes)!==wire.ciphertext_sha256)throw new Error('continuity_ciphertext_mismatch');
  const key=await crypto.subtle.importKey('raw',keyBytes,'AES-GCM',false,['decrypt']);
  const compressed=new Uint8Array(await crypto.subtle.decrypt({name:'AES-GCM',iv:decode(wire.iv),
    additionalData:new TextEncoder().encode(canonical(boundary))},key,bytes));
  const plaintext=new Uint8Array(await new Response(new Blob([compressed]).stream().pipeThrough(new DecompressionStream('gzip'))).arrayBuffer());
  if(await digest(plaintext)!==wire.verified_plaintext_sha256)throw new Error('continuity_plaintext_mismatch');
  const records=JSON.parse(new TextDecoder().decode(plaintext));
  if(records.length!==boundary.record_count || await digest(new TextEncoder().encode(canonical(records)))!==boundary.source_hash)
    throw new Error('continuity_source_mismatch');
  return records;
}
