"""Pure preflight oracle, not authorization or a transaction/commit implementation."""
from .contracts import content_hash


def classify_items(proposal, current_versions, committed_items):
    if content_hash(proposal) != proposal["content_hash"]:
        raise ValueError("Proposal hash mismatch")
    ids = [item["item_id"] for item in proposal["items"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate proposal item IDs")
    known = set(ids)
    def version_key(e):
        return e["record_type"], e["record_id"], e["record_version"]
    expected_union = {version_key(e) for item in proposal["items"] for e in item["expected_record_versions"]}
    if expected_union != {version_key(e) for e in proposal["expected_record_versions"]}:
        raise ValueError("Proposal expected-version summary must equal item dependency union")
    results = {}
    visiting = set()
    by_id = {item["item_id"]: item for item in proposal["items"]}

    def inspect(item_id):
        if item_id in results:
            return results[item_id]
        if item_id in visiting:
            raise ValueError("Cyclic proposal item dependencies")
        visiting.add(item_id)
        item = by_id[item_id]
        dependencies_by_record = {(e["record_type"], e["record_id"]): e["record_version"] for e in item["expected_record_versions"]}
        if len(dependencies_by_record) != len(item["expected_record_versions"]):
            raise ValueError("Duplicate or contradictory item expected versions")
        dependencies = item["depends_on_item_ids"]
        if any(dep not in known for dep in dependencies):
            raise ValueError("Unknown proposal dependency")
        dependency_states = [inspect(dep) for dep in dependencies]
        # Committed evidence is looked up before source freshness: restart must not reinterpret it.
        prior = committed_items.get((proposal["id"], item_id))
        if prior is not None:
            if prior != proposal["content_hash"]:
                raise ValueError("Idempotency hash conflict")
            result = "committed"
        elif any(s not in {"valid", "committed"} for s in dependency_states):
            result = "blocked"
        elif item["unresolved_ambiguity"]:
            result = "ambiguous"
        elif any(e["verification"] == "conflicting" for e in item["evidence"]):
            result = "conflicting"
        elif any(e["verification"] != "verified" for e in item["evidence"]):
            result = "invalid"
        elif any(op["operation"].startswith("task.") and
                 dependencies_by_record.get(("task", op["arguments"]["task_id"])) != op["arguments"]["expected_version"]
                 for op in item["proposed_operations"]):
            result = "invalid"
        elif any(current_versions.get((e["record_type"], e["record_id"])) != e["record_version"]
                 for e in item["expected_record_versions"]):
            result = "stale"
        else:
            result = "valid"
        visiting.remove(item_id)
        results[item_id] = result
        return result

    for item_id in ids:
        inspect(item_id)
    return results
