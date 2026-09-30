import {createClient} from 'https://esm.sh/@supabase/supabase-js@2.117.2';
const origin='https://loonpojawpfagzobxoko.supabase.co';
const publishable='sb_publishable_A19eRlBW-_lg1-aL4vtwTQ_VEf6IzgH';
const callback='https://gardnerdarrell1010-collab.github.io/ecos-2x/oauth/consent/';
const status=document.querySelector('#status');
const login=document.querySelector('#login');
const consent=document.querySelector('#consent');
const client=createClient(origin,publishable,{auth:{flowType:'pkce',storage:sessionStorage,persistSession:true,detectSessionInUrl:false}});
const current=new URL(location.href);
let authorization=current.searchParams.get('authorization_id');
if(authorization)sessionStorage.setItem('ecos.authorization',authorization);
else authorization=sessionStorage.getItem('ecos.authorization');
const message=(value)=>{status.textContent=value;};
const validAuthorization=()=>typeof authorization==='string'&&/^[0-9a-f-]{36}$/i.test(authorization);
async function load(){
  if(current.searchParams.has('error')){history.replaceState({},'',location.pathname);message('Sign-in was not completed. Restart the ChatGPT connection flow.');return;}
  if(current.searchParams.has('code')){
    const code=current.searchParams.get('code');history.replaceState({},'',location.pathname);
    const {error}=await client.auth.exchangeCodeForSession(code);
    if(error){message('Sign-in could not be verified. Restart the ChatGPT connection flow.');return;}
  }
  if(!validAuthorization()){message('Open this page from the ChatGPT ECOS connection authorization flow.');return;}
  const {data:{user}}=await client.auth.getUser();
  if(!user){
    const response=await fetch(origin+'/auth/v1/settings',{headers:{apikey:publishable}});
    const settings=await response.json();
    if(!settings.external?.github){message('The dedicated GitHub sign-in provider is awaiting owner configuration.');return;}
    login.disabled=false;message('Continue to GitHub to sign in.');return;
  }
  const {data,error}=await client.auth.oauth.getAuthorizationDetails(authorization);
  if(error||!data){message('Authorization request unavailable. Restart the ChatGPT connection flow.');return;}
  if(!('authorization_id' in data)){message('This authorization was already handled. Return to ChatGPT.');return;}
  document.querySelector('#client').textContent=data.client?.name||'OAuth application';
  document.querySelector('#scopes').textContent='Requested scopes: '+(data.scope||'None');
  document.querySelector('#redirect').textContent='Return address: '+(data.redirect_uri||'Provided by the authorization server');
  login.hidden=true;consent.hidden=false;message('Review this application before approving.');
}
login.addEventListener('click',async()=>{
  if(!validAuthorization())return;
  login.disabled=true;
  const {error}=await client.auth.signInWithOAuth({provider:'github',options:{redirectTo:callback,scopes:'read:user user:email'}});
  if(error){message('GitHub sign-in could not start.');login.disabled=false;}
});
async function decide(approve){
  for(const button of consent.querySelectorAll('button'))button.disabled=true;
  const {error}=approve?await client.auth.oauth.approveAuthorization(authorization):await client.auth.oauth.denyAuthorization(authorization);
  if(error){message('The decision could not be recorded. Restart the authorization flow.');return;}
  sessionStorage.removeItem('ecos.authorization');
}
document.querySelector('#approve').addEventListener('click',()=>decide(true).catch(()=>message('Authorization failed.')));
document.querySelector('#deny').addEventListener('click',()=>decide(false).catch(()=>message('Authorization failed.')));
load().catch(()=>message('Authorization is unavailable. Restart the connection flow.'));
