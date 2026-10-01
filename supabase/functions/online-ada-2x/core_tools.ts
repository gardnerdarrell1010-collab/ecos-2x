import { z } from 'npm:zod@4.6.5';
import { canonical,decode,digest,encryptSnapshot,verifySnapshot } from './continuity_core.mjs';

export function registerCoreTools(server:any,database:any,identity:any) {
 const request=(id:string,op:string,args:any)=>({schema_version:'1.0.0',context:{principal_id:identity.principal,
  executor_instance_id:identity.instance,correlation_id:id,causation_id:null,idempotency_key:id+':'+op},arguments:args});
 const operate=async(id:string,op:string,args:any)=>{
  const rows=await database`select ecos.operate(${op},${database.json(request(id,op,args))}) as response`;
  if(rows[0].response.code)throw new Error(rows[0].response.code);return rows[0].response;
 };
 const read=async(kind:string,id:string)=>(await database`select ecos.read_record(${kind},${id}::uuid) as response`)[0].response.record;
 const fence=z.object({claim_id:z.string().uuid(),occurrence_id:z.string().uuid(),stage_definition_id:z.string().uuid(),
  claim_version:z.number().int(),fence_token:z.string().uuid(),executor_instance_id:z.string().uuid()});
 server.registerTool('ecos_continuity_checkpoint',{
  description:'A018 only. Export explicitly granted core records into an encrypted immutable PostgreSQL continuity package; verify stored manifest, ciphertext and decrypted parity before completing the claim. Does not roll over memory or claim a full database restore test.',
  inputSchema:z.object({request_id:z.string().uuid(),fence,execution_run_id:z.string().uuid()}),
  annotations:{readOnlyHint:false,destructiveHint:false,openWorldHint:false},
 },async(a:any)=>{
  try {
   const pkg=(await operate(a.request_id,'work.package',{fence:a.fence})).data;
   if(pkg.stage.stage_key!=='incremental_continuity')throw new Error('forbidden');
   const key=decode(Deno.env.get('ECOS_CONTINUITY_ENCRYPTION_KEY')||'');
   if(key.length!==32)throw new Error('continuity_key_unavailable');
   const snapshot=(await operate(a.request_id,'continuity.snapshot',{fence:a.fence})).data;
   const {records,...boundary}=snapshot;
   const encrypted=await encryptSnapshot(records,boundary,key,a.request_id);
   const value=(await operate(a.request_id,'continuity.checkpoint.commit',{
    fence:a.fence,package_id:a.request_id,boundary,...encrypted})).data;
   const saved=await read('export_package',value.package_id);
   if(await digest(new TextEncoder().encode(canonical(saved.manifest)))!==value.manifest_hash || saved.content_hash!==value.manifest_hash)
    throw new Error('continuity_inventory_mismatch');
   const bytesByPath:any={};
   for(const [path,id] of Object.entries(value.files)){
    const artifact=await read('artifact',id as string);const encoded=artifact.uri.split(';base64,');
    if(encoded.length!==2)throw new Error('continuity_inventory_mismatch');
    const bytes=decode(encoded[1]);const entry=saved.manifest.files.find((x:any)=>x.path===path);
    if(!entry || bytes.length!==entry.size_bytes || await digest(bytes)!==entry.sha256 || artifact.content_hash!==entry.sha256)
     throw new Error('continuity_inventory_mismatch');
    bytesByPath[path]=encoded[1];
   }
   await verifySnapshot({...encrypted,ciphertext:bytesByPath['records.aes-gcm']},boundary,key);
   const backup=await read('backup_record',value.backup_id);
   if(backup.manifest_hash!==value.manifest_hash || !backup.encrypted)throw new Error('continuity_inventory_mismatch');
   const at=new Date().toISOString();
   const result={id:a.request_id,schema_version:'1.0.0',created_at:at,occurrence_id:a.fence.occurrence_id,
    stage_definition_id:a.fence.stage_definition_id,execution_run_id:a.execution_run_id,
    result_schema_id:pkg.stage.result_schema_id,content_hash:await digest(new TextEncoder().encode(canonical(value))),
    artifact_uri:'ecos:export-package:'+value.package_id,verified_at:at,verified_by:identity.principal,source_references:pkg.source_references};
   const completion=await operate(a.request_id,'work.complete',{fence:a.fence,result});
   return {content:[{type:'text',text:JSON.stringify({package_id:value.package_id,record_count:boundary.record_count,
    source_hash:boundary.source_hash,independent_parity_verified:true,full_database_backup:false,restore_test_performed:false,completion})}]};
  }catch(e){const message=e instanceof Error?e.message:'';return {isError:true,content:[{type:'text',text:
   ['forbidden','gate_blocked','stale_version','continuity_key_unavailable'].includes(message)?message:'continuity_failed_preserve_request_id'}]};}
 });
}
