"""Materialize reviewed, entirely synthetic positive/negative contract examples."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT),str(ROOT/"src")]
from ecos.core.contracts import ContractStore
from tests.fixtures import bootstrap, proposal, specimen, task


def build():
    store = ContractStore(ROOT)
    cases = []
    def add(name,schema,payload,valid):
        cases.append({"name":name,"schema":schema,"valid":valid,"payload":payload})
    add("independent_obligation","task",task(),True)
    add("runtime_leak_into_task","task",task()|{"claim_version":1},False)
    add("compound_lifecycle","task",task()|{"lifecycle_state":"Completed Pending ACK"},False)
    add("bad_timestamp","task",task()|{"created_at":"yesterday"},False)
    add("review_siblings","semantic_proposal",proposal(),True)
    add("self_contained_bootstrap","bootstrap_package",bootstrap(store),True)
    for name in ("domain_event","provider_receipt","provider_command","work_occurrence","memory_version"):
        payload = specimen(store.schemas["https://contracts.ecos.invalid/v1/"+name+".schema.json"],store)
        add("synthetic_"+name,name,payload,True)
    return {"synthetic_only":True,"cases":cases}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check",action="store_true")
    args = parser.parse_args()
    path = ROOT/"db/fixtures/contract-examples.json"
    content = json.dumps(build(),ensure_ascii=False,indent=2)+"\n"
    if args.check:
        if path.read_text(encoding="utf-8") != content:
            raise SystemExit("Synthetic fixture drift")
    else:
        path.write_text(content,encoding="utf-8",newline="\n")
    print("Verified synthetic examples" if args.check else "Generated synthetic examples")
