"""Offline checks for Phase 2 release; no database or provider access."""
import hashlib,json,re,subprocess
from pathlib import Path
from migrations import inventory
ROOT=Path(__file__).resolve().parents[1]
def main():
    git=['C:/Program Files/Git/cmd/git.exe','-c','safe.directory=C:/ecos/ecos-2x','-C',str(ROOT)]
    items=inventory(ROOT/'db/migrations');assert len(items)==20
    for m in items[:18]:
        baseline=subprocess.check_output(git+['show','c5731953a29256c013597cb04b938dff41f56de0:db/migrations/'+m['name']])
        assert hashlib.sha256(baseline).hexdigest()==m['sha256'],m['name']
    test=json.loads((ROOT/'docs/evidence/phase2/clean-candidate-008.json').read_text())
    assert test['status']=='passed'
    assert test['catalog']['ledger']==[{k:v for k,v in m.items() if k!='sql'} for m in items]
    assert all(x['status']=='passed' for x in test['concurrency'].values())
    patterns={'private_key':r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----','github_token':r'gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}','openai_key':r'sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}','aws_access_key':r'AKIA[0-9A-Z]{16}','database_url_password':r'postgres(?:ql)?://[^\s:/]+:[^\s@]+@','supabase_key':r'sbp_[a-zA-Z0-9]{30,}'}
    files=list(filter(None,subprocess.check_output(git+['ls-files','--cached','--others','--exclude-standard','-z']).decode().split('\0')))
    files=[name for name in files if (ROOT/name).is_file()]
    findings=[]
    for name in files:
        text=(ROOT/name).read_bytes().decode('utf-8',errors='replace')
        for label,pattern in patterns.items():
            if re.search(pattern,text):findings.append({'path':name,'pattern':label})
    result={'status':'passed' if not findings else 'failed','accepted_migrations_1_to_18':'byte-identical','candidate_head':20,'tested_ledger_matches_files':True,'files_scanned':len(files),'secret_pattern_findings':findings,'canonical_secret_retrieved':False,'exact_secret_comparison':'not needed; no persistent credentials retrieved','patterns':list(patterns)}
    (ROOT/'docs/evidence/phase2/clean-release-check.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(result));assert not findings
if __name__=='__main__':main()
