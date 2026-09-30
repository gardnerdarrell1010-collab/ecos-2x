from copy import deepcopy
from uuid import UUID

from ecos.core.contracts import content_hash

NOW = "2026-09-28T12:00:00+00:00"
ZERO_HASH = "0" * 64


def uid(number=1):
    return str(UUID(int=number, version=4))


def reference(number=1, version=1):
    return {"record_type":"task", "record_id":uid(number), "record_version":version,
        "content_hash":ZERO_HASH, "authority":"structured_ecos"}


def evidence(number=1):
    return {"source":reference(number), "assertion":"Synthetic evidence", "verification":"verified"}


def task():
    return {"id":uid(), "schema_version":"1.0.0", "created_at":NOW, "record_version":1,
        "business_id":"SYNTHETIC-TASK-1", "title":"Synthetic obligation", "description":"Offline fixture",
        "project_id":None, "lifecycle_state":"open", "wait_reason":"none"}


def proposal():
    items = []
    for n in (1, 2):
        items.append({"item_id":uid(n+100), "depends_on_item_ids":[], "source_references":[reference(n)],
            "expected_record_versions":[{"record_type":"task","record_id":uid(n),"record_version":1}],
            "proposed_operations":[{"operation":"task.transition","arguments":{
                "task_id":uid(n),"expected_version":1,"target_state":"waiting","wait_reason":"owner",
                "reason_code":"owner_input","evidence":[evidence(n)]}}],
            "evidence":[evidence(n)], "confidence_basis_points":9000,"unresolved_ambiguity":[]})
    value = {"id":uid(200), "proposal_type":"synthetic_review", "schema_version":"1.0.0", "created_at":NOW,
        "correlation_id":uid(201), "source_references":[reference(1),reference(2)],
        "expected_record_versions":[r for item in items for r in item["expected_record_versions"]],
        "items":items, "content_hash":ZERO_HASH}
    value["content_hash"] = content_hash(value)
    return value


def rehash(value):
    result = deepcopy(value)
    result["content_hash"] = content_hash(result)
    return result


def bootstrap(store):
    base = "https://contracts.ecos.invalid/v1/"
    request_id = base+"task.transition-request.schema.json"
    response_id = base+"operation_result.schema.json"
    task_id = base+"task.schema.json"
    bundle = {}
    def collect(schema_id):
        schema_id = schema_id.split("#")[0]
        if schema_id in bundle:
            return
        document = store.schemas[schema_id]
        bundle[schema_id] = {"schema_id":schema_id,"sha256":content_hash(document),"document":document}
        def walk(node):
            if isinstance(node,dict):
                if "$ref" in node:
                    collect(node["$ref"])
                for child in node.values():
                    walk(child)
            elif isinstance(node,list):
                for child in node:
                    walk(child)
        walk(document)
    for schema_id in (request_id,response_id,task_id):
        collect(schema_id)
    source = reference() | {"content_hash":content_hash(task())}
    return rehash({"package_id":uid(500),"schema_version":"1.0.0","database_schema_version":"synthetic-phase0",
        "generated_at":NOW,"principal_id":uid(501),"sensitivity_ceiling":"internal","governed_context":[source],
        "context_records":[{"source":source,"record_schema_id":task_id,"record":task()}],
        "active_memory_heads":[],"unresolved_exceptions":[],"operation_schema_ids":[request_id,response_id],
        "operation_bindings":[{"operation":"task.transition","path":"/v1/operations/task.transition",
            "request_schema_id":request_id,"response_schema_id":response_id}],
        "schema_bundle":list(bundle.values()),"capability_vocabulary":["db.governed_operations"],
        "relevant_work":[],"content_hash":ZERO_HASH})


def specimen(schema, store):
    """Generate a structural fixture for each published schema, not business evidence."""
    if "$ref" in schema:
        base, _, fragment = schema["$ref"].partition("#")
        schema = store.schemas[base]
        if fragment:
            for part in fragment.lstrip("/").split("/"):
                schema = schema[part.replace("~1","/").replace("~0","~")]
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    if "anyOf" in schema:
        if any(branch.get("type") == "null" for branch in schema["anyOf"]):
            return None
        return specimen(schema["anyOf"][0], store)
    if "oneOf" in schema:
        return specimen(schema["oneOf"][0], store)
    kind = schema.get("type", "object")
    if kind == "object":
        value = {key:specimen(schema["properties"][key], store) for key in schema.get("required", [])}
        if schema.get("title") == "domain_event":
            value["aggregate_type"] = "task"
        return value
    if kind == "array":
        count = schema.get("minItems", 0)
        if schema.get("uniqueItems") and count > 1:
            item_schema = schema["items"]
            if "$ref" in item_schema:
                base, _, fragment = item_schema["$ref"].partition("#")
                item_schema = store.schemas[base]
                for part in fragment.lstrip("/").split("/"):
                    item_schema = item_schema[part]
            return item_schema["enum"][:count]
        return [specimen(schema["items"], store) for _ in range(count)]
    if kind == "integer":
        return schema.get("minimum", 0)
    if kind == "boolean":
        return False
    if kind == "null":
        return None
    if kind == "string":
        if schema.get("format") == "uuid":
            return uid()
        if schema.get("format") == "date":
            return "2026-09-27"
        if schema.get("format") == "date-time":
            return NOW
        pattern = schema.get("pattern", "")
        if "a-f0-9" in pattern:
            return ZERO_HASH
        if "TASK-AUTO" in pattern:
            return "TASK-AUTO-000001"
        if pattern.startswith("^A["):
            return "A001"
        return "synthetic"
    raise ValueError(kind)
