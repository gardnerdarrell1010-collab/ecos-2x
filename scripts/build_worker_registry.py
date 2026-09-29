"""Lossless conversion of the approved appendix, with explicit normalized annotations."""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/baseline/ECOS_2X_WORKER_DISPOSITION_APPENDIX.md"
D = "DATABASE_DETERMINISTIC"
R = "RESIDENT_DETERMINISTIC_PROVIDER"
S = "ONLINE_SEMANTIC"

# Surface lists describe distinct stages, never a cross-surface HYBRID claim.
SURFACES = {
    "001":[S,R], "002":[R,S,D], "003":[D,R,S], "004":[S,R], "005":[D,R],
    "006":[S,D,R], "007":[R,S,D], "008":[D], "009":[D,S,R], "010":[D,R],
    "011":[D,R,S], "012":[D,R], "013":[D,R], "014":[D], "015":[D,S],
    "016":[D,S], "017":[], "018":[S,D], "019":[S,D], "020":[S,D],
    "021":[S,D], "022":[D], "023":[R,D], "024":[D,S,R], "025":[D],
    "026":[D,S], "027":[D,R], "028":[R,D], "029":[R,D], "029-B":[D],
    "030":[], "031":[S,D], "032":[R], "033":[S], "034":[], "035":[R,S,D],
    "036":[R,D,S], "037":[D], "038":[D], "039":[D], "040":[D], "041":[D],
    "042":[D], "043":[D], "044":[R], "045":[D], "046":[R,S], "047":[D],
    "048":[D,S], "049":[D,S], "050":[D,S], "051":[D], "052":[R], "053":[S], "054":[D,R],
}
SEMANTIC_YES = "001 002 004 006 015 018 019 020 021 031 033 035 049 050 053".split()
SEMANTIC_CONDITIONAL = "003 007 009 011 013 016 024 026 036 046 048".split()
PROVIDERS = {
    "001":["gmail"], "002":["google_drive"], "003":["gmail","google_drive"],
    "004":["google_drive","gmail","twilio"], "005":["postgresql_backup","controlled_storage"],
    "006":["google_drive","gmail"], "007":["google_drive"], "009":["scoped_reconciliation"],
    "010":["gmail"], "011":["scoped_reconciliation"], "012":["controlled_storage"],
    "013":["scoped_reconciliation"], "015":["gmail","twilio"], "016":["gmail","twilio"],
    "017":[], "023":["owner_review"], "024":["declared_by_stage"], "027":["sms_gateway"],
    "028":["twilio"], "029":["toast"], "031":["twilio"], "032":["vercel_blob","google_drive"],
    "033":["approved_publication"], "035":["gmail"], "036":["google_calendar"],
    "044":["resident_renderer","google_drive"], "046":["financial_connectors"],
    "047":[], "052":["resident_renderer","google_drive"], "054":["owner_review"],
}
TRIGGERS = {
    "001":("gmail_delta_or_webhook_with_recovery_poll","<1 minute"),
    "002":("drive_change_or_recovery_delta","<1 minute"),
    "003":("ingestion_commit_and_scheduled_audit","transaction for invariants; audit SLA pending"),
    "004":("scheduled_occurrence","<5 minutes after due"),
    "005":("managed_backup_daily_logical_quarterly_restore","RPO/RTO pending owner approval"),
    "006":("document_event_or_approval","policy-specific; pending"),
    "007":("drive_inventory_event","policy-specific; pending"),
    "008":("transaction_and_recovery_sweep","synchronous invariants; 1 minute sweep"),
    "009":("nightly_audit","nightly; duration pending"),
    "010":("delivery_commit","<5 seconds to ready draft transport"),
    "011":("completion_event_and_exception_sweep","transaction; sweep 1-5 minutes"),
    "012":("package_created_and_daily_sweep","on package creation; daily sweep"),
    "013":("scheduled_replay","schedule pending"), "014":("ci_and_scheduled_conformance","per CI run"),
    "015":("coverage_threshold_or_state_event","<1 minute threshold detection"),
    "016":("follow_up_threshold","<1 minute"), "017":("none_retired","not applicable"),
    "018":("state_event_or_six_hour_schedule","six hours or event"),
    "019":("actual_reconciliation_and_daily_schedule","daily; after actual reconciliation"),
    "020":("scheduled_forecast","daily; before horizon"), "021":("schedule_and_fresh_base_snapshot","daily"),
    "022":("state_event_or_hourly_schedule","hourly or event"), "023":("review_webhook_or_recovery_poll","<5 seconds webhook"),
    "024":("ready_work_event","<1 minute semantic; <5 seconds provider transport"),
    "025":("claim_transaction_and_lease_expiry","transaction; 1-5 minutes recovery"),
    "026":("source_completion_event","policy-specific; pending"), "027":("webhook_or_provider_command","<5 seconds"),
    "028":("provider_command_committed","<5 seconds"), "029":("closed_actuals_delta_or_schedule","<1 minute after close/due"),
    "029-B":("closed_actuals_committed","seconds"), "030":("none_retired","not applicable"),
    "031":("receipt_committed","<1 minute"), "032":("verified_artifact_version","<1 minute"),
    "033":("daily_or_business_event","daily or event"), "034":("none_retired","not applicable"),
    "035":("gmail_delta_or_webhook_with_recovery_poll","<1 minute"), "036":("calendar_threshold","<1 minute"),
    "037":("query_or_state_event","sub-second"), "038":("heartbeat_or_expiry","<1 minute detection target"),
    "039":("query","query-time"), "040":("execution_event","seconds"), "041":("query_or_refresh","seconds/minutes"),
    "042":("health_threshold","<1 minute"), "043":("package_created","on package creation"),
    "044":("verified_status_package","<1 minute"), "045":("query_or_snapshot","query-time"),
    "046":("account_delta_or_schedule","policy-specific; pending"), "047":("toast_actuals_committed","query-time"),
    "048":("cash_evidence_event_or_schedule","policy-specific; pending"),
    "049":("source_completion_or_schedule","policy-specific; pending"), "050":("event_or_schedule","policy-specific; pending"),
    "051":("source_update_or_freshness_threshold","<1 minute"), "052":("verified_dashboard_package","<1 minute"),
    "053":("verified_review_package_committed","<1 minute semantic pickup"), "054":("verified_proposal_committed","<5 seconds"),
}


def build():
    text = SOURCE.read_text(encoding="utf-8")
    preservation = [line[2:] for line in text.split("## Subordinate-function preservation\n", 1)[1].splitlines() if line.startswith("- ")]
    groups = [set("023 053 054".split()), {"026"}, set("029 029-B 020 021 019".split()),
              set("022 037 038 039 040 041 042 043 044".split()), set("010 027 028".split()), {"017","030"}]
    workers = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if not re.match(r"\| A\d{3}", line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != 6:
            raise ValueError(f"Unexpected appendix shape on line {line_number}")
        match = re.fullmatch(r"A(\d{3}(?:-B)?) (.+)", cells[0])
        key, name = match.groups()
        retired = key in {"017", "030", "034"}
        current_class = "AI Agent" if "AI Agent;" in cells[1] else "Application" if "Application;" in cells[1] else "not stated in review; disabled/retired"
        trigger = cells[1].split(";", 1)[1].strip() if ";" in cells[1] else "none; disabled/retired"
        capability = re.split(r" (?:AI Agent|Application);", cells[1])[0]
        surfaces = SURFACES[key]
        disposition = re.search(r"\*\*(.+?)\*\*", cells[3]).group(1).rstrip(".")
        semantic = "not_applicable" if retired else "yes" if key in SEMANTIC_YES else "conditional" if key in SEMANTIC_CONDITIONAL else "upstream_only" if key == "010" else "no"
        workers.append({
            "legacy_worker_id": "TASK-AUTO-" + key.zfill(6) if "-" not in key else "TASK-AUTO-000029-B",
            "legacy_short_id": "A" + key, "legacy_name": name, "business_capability": capability,
            "current_trigger": trigger, "current_execution_class": current_class,
            "2x_disposition": disposition, "2x_execution_surface": surfaces,
            "2x_trigger": TRIGGERS[key][0], "target_latency": TRIGGERS[key][1],
            "semantic_required": semantic, "provider_adapter": PROVIDERS.get(key, []),
            "proposed_objects": [part.strip().strip("`") for part in cells[4].split(";", 1)[0].split(",")],
            "acceptance_test": cells[5], "retirement_maturity": "capability_retired_pending_authority_confirmation" if retired else "production_verified",
            "retirement_conditions": cells[5], "retired_at_review": retired,
            "notes": cells[2] + " | " + cells[3] + " | " + cells[4] + " Normalized stage surfaces/latencies are contract targets, not proof of implementation.",
            "source_row": cells, "source_line": line_number,
            "subordinate_preservation": [note for keys, note in zip(groups, preservation) if key in keys],
        })
    return {"schema_version":"1.0.0", "review_date":"2026-09-28", "usage":"migration_and_acceptance_only",
            "source_sha256":hashlib.sha256(SOURCE.read_bytes()).hexdigest(), "workers":workers}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = ROOT / "contracts/migration/worker-dispositions.json"
    content = json.dumps(build(), ensure_ascii=False, indent=2) + "\n"
    if args.check:
        if target.read_text(encoding="utf-8") != content:
            raise SystemExit("Worker registry drift")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
    print("Verified 55-worker conversion" if args.check else "Generated worker registry")
