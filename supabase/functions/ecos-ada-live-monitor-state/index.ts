import { withSupabase } from "npm:@supabase/server";
const headers={"access-control-allow-origin":"*","access-control-allow-methods":"GET, OPTIONS","access-control-allow-headers":"content-type","cache-control":"no-store","content-type":"application/json; charset=utf-8"};
export default {fetch:withSupabase({auth:"none"},async(req,ctx)=>{
if(req.method==="OPTIONS")return new Response(null,{status:204,headers});
if(req.method!=="GET")return Response.json({error:"method_not_allowed"},{status:405,headers});
const {data,error}=await ctx.supabaseAdmin.rpc("ecos_monitor_snapshot");
if(error)return Response.json({error:"monitor_read_failed"},{status:503,headers});
return Response.json(data,{headers});
})};

