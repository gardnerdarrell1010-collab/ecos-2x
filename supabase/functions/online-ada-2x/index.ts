import { registerGmailTools } from './gmail_tools.ts';
import { createMcpHandler, McpServer } from 'npm:@modelcontextprotocol/server@2.2.0';
import { createRemoteJWKSet, jwtVerify } from 'npm:jose@6.2.12';
import postgres from 'npm:postgres@3.4.9';
import { z } from 'npm:zod@4.6.5';
import { OPERATIONS, boundRequest, authorizedClaims, databaseLoginAllowed } from './online_transport_core.mjs';

// All configuration is server-side. Missing enrollment fails closed.
const env = (name: string) => Deno.env.get(name) ?? '';
const project = env('SUPABASE_URL');
const resource = `${project}/functions/v1/online-ada-2x`;
const issuer = `${project}/auth/v1`;
const identity = {
  principal: env('ECOS_ONLINE_PRINCIPAL_ID'), instance: env('ECOS_ONLINE_INSTANCE_ID'),
  subject: env('ECOS_ONLINE_OAUTH_SUBJECT'), client: env('ECOS_ONLINE_OAUTH_CLIENT_ID'),
};
const dbUrl = env('ECOS_ONLINE_DATABASE_URL');
const configured = Object.values(identity).every(Boolean) && !!dbUrl && databaseLoginAllowed(dbUrl);
const jwks = createRemoteJWKSet(new URL(`${issuer}/.well-known/jwks.json`));
const database = configured ? postgres(dbUrl, {
  max: 1, prepare: false, idle_timeout: 10, connect_timeout: 10,
  ssl: { rejectUnauthorized: true, ...(env('ECOS_ONLINE_DATABASE_CA') ? {ca:env('ECOS_ONLINE_DATABASE_CA')} : {}) },
}) : null;
const json = (value: unknown, status = 200, headers = {}) => Response.json(value, {
  status, headers: {'Cache-Control':'no-store', ...headers},
});

Deno.serve(async (req: Request) => {
  const url = new URL(req.url);
  if (req.method === 'GET' && ['/online-ada-2x/oauth-protected-resource','/functions/v1/online-ada-2x/oauth-protected-resource'].includes(url.pathname)) {
    return json({resource, authorization_servers:[issuer], bearer_methods_supported:['header']});
  }
  const token = req.headers.get('Authorization')?.match(/^Bearer (\S+)$/)?.[1];
  if (!token) return json({error:'authentication_required'},401, {
    'WWW-Authenticate':`Bearer resource_metadata="${resource}/oauth-protected-resource"`,
  });
  if (!configured || !database) return json({error:'online_enrollment_unavailable'},503);
  try {
    const {payload} = await jwtVerify(token,jwks,{
      issuer, audience: env('ECOS_ONLINE_OAUTH_AUDIENCE') || 'authenticated',
      algorithms:['ES256','RS256'], requiredClaims:['sub','exp','iat','client_id'],
    });
    if (!authorizedClaims(payload,identity)) return json({error:'executor_not_authorized'},403);
  } catch { return json({error:'invalid_access_token'},401); }
  if (!['POST','GET','DELETE'].includes(req.method)) return json({error:'method_not_allowed'},405);
  if (Number(req.headers.get('Content-Length') || 0) > 262144) return json({error:'request_too_large'},413);
  let boundedHttpRequest = req;
  if (req.method === 'POST') {
    const reader = req.body?.getReader();
    if (!reader) return json({error:'invalid_request'},400);
    const chunks: Uint8Array[] = []; let bytes = 0;
    while (true) {
      const {done,value} = await reader.read();
      if (done) break;
      bytes += value.length;
      if (bytes > 262144) { await reader.cancel(); return json({error:'request_too_large'},413); }
      chunks.push(value);
    }
    const body = new Uint8Array(bytes); let offset = 0;
    for (const chunk of chunks) { body.set(chunk,offset); offset += chunk.length; }
    boundedHttpRequest = new Request(req.url,{method:req.method,headers:req.headers,body});
  }
  // The official SDK implements MCP framing. Each request has a fresh server.
  const handler = createMcpHandler(() => {
    const server = new McpServer({name:'ecos-online-ada-2x',version:'0.1.0'});
    server.registerTool('ecos_identity', {
      description:'Return the enrolled Online executor context. Contains no credentials.',
      inputSchema:z.object({}),annotations:{readOnlyHint:true,openWorldHint:false},
    },()=>({content:[{type:'text',text:JSON.stringify({identity:'ONLINE_ADA_2X',
      principal_id:identity.principal,executor_instance_id:identity.instance})}]}));
    server.registerTool('ecos_operate', {
      description:'Invoke an accepted ECOS operation as ONLINE_ADA_2X. PostgreSQL enforces authorization, capabilities, authority, claim fencing and idempotency. No SQL access.',
      inputSchema:z.object({operation:z.enum(OPERATIONS as [string,...string[]]),request:z.record(z.string(),z.unknown())}),
      annotations:{readOnlyHint:false,destructiveHint:true,openWorldHint:false},
    },async ({operation,request}) => {
      let bounded;
      try { bounded=boundRequest(operation,request,identity); }
      catch { return {isError:true,content:[{type:'text',text:'transport_request_rejected'}]}; }
      try {
        const result = await database.begin(async (sql) => {
          await sql`set local statement_timeout = '20s'`;
          return await sql`select ecos.operate(${operation},${sql.json(bounded)}) as response`;
        });
        return {content:[{type:'text',text:JSON.stringify(result[0].response)}]};
      } catch {
        // Do not leak database URLs, raw errors, tokens, or request bodies.
        // An uncertain response must be reconciled with the same governed key.
        return {isError:true,content:[{type:'text',text:'operation_outcome_unknown_preserve_idempotency_key'}]};
      }
    });
    server.registerTool('ecos_read_record', {
      description:'Read an explicitly assigned ECOS record. PostgreSQL enforces object and domain grants; this does not enumerate or grant access.',
      inputSchema:z.object({kind:z.enum(['communication','communication_processing','provider_receipt','task','project','party','relationship','notification','delivery','work_occurrence']),id:z.string().uuid()}),
      annotations:{readOnlyHint:true,openWorldHint:false},
    },async ({kind,id}) => {
      try {
        const rows=await database`select ecos.read_record(${kind},${id}::uuid) as response`;
        return {content:[{type:'text',text:JSON.stringify(rows[0].response)}]};
      } catch { return {isError:true,content:[{type:'text',text:'record_not_authorized_or_unavailable'}]}; }
    });
    registerGmailTools(server,database,identity);
    return server;
  });
  return handler.fetch(boundedHttpRequest);
});
