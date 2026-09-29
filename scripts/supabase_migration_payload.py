"""Render a tool payload offline. This script does not connect or apply SQL."""
import argparse,json
from migrations import ROOT,inventory,render
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--project-ref',required=True,choices=['loonpojawpfagzobxoko'])
a=p.parse_args()
m=inventory(ROOT/'db/migrations')
q=render(m).replace('\\set ON_ERROR_STOP on\n','',1).replace('begin;\n','',1)
q=q.rsplit('commit;',1)[0]
print(json.dumps({'project_id':a.project_ref,'name':f"ecos_phase1_{m[-1]['version']:06d}",'query':q}))
