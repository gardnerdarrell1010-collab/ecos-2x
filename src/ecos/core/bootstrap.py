"""Verify a self-contained bootstrap contract bundle without external retrieval."""
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from .contracts import content_hash


def verify_bootstrap(package, store):
    store.validate("bootstrap_package",package)
    if content_hash(package) != package["content_hash"]:
        raise ValueError("Bootstrap package hash mismatch")
    schemas = {}
    for entry in package["schema_bundle"]:
        schema_id, document = entry["schema_id"], entry["document"]
        if schema_id in schemas or document["$id"] != schema_id or content_hash(document) != entry["sha256"]:
            raise ValueError("Invalid bootstrap schema identity/hash")
        Draft202012Validator.check_schema(document)
        schemas[schema_id] = document
    registry = Registry().with_resources((id_,Resource.from_contents(doc)) for id_,doc in schemas.items())
    def check_refs(node,resolver):
        if isinstance(node,dict):
            if "$ref" in node:
                resolver.lookup(node["$ref"])
            for child in node.values():
                check_refs(child,resolver)
        elif isinstance(node,list):
            for child in node:
                check_refs(child,resolver)
    for id_,doc in schemas.items():
        check_refs(doc,registry.resolver(id_))
    declared = set(package["operation_schema_ids"])
    bound = set()
    for binding in package["operation_bindings"]:
        bound.update((binding["request_schema_id"],binding["response_schema_id"]))
    if declared != bound or not declared <= schemas.keys():
        raise ValueError("Incomplete operation schema bundle")
    for record in package["context_records"]:
        source, value = record["source"], record["record"]
        if source["record_id"] != value.get("id") or content_hash(value) != source["content_hash"]:
            raise ValueError("Context identity/hash mismatch")
        if "record_version" in value and value["record_version"] != source["record_version"]:
            raise ValueError("Context version mismatch")
        schema = schemas[record["record_schema_id"]]
        Draft202012Validator(schema,registry=registry,format_checker=FormatChecker()).validate(value)
    return len(schemas)
