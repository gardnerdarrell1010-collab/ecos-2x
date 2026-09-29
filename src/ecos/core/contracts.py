from __future__ import annotations

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


def canonical_bytes(value):
    """ECOS JSON profile v1: string keys, integers, booleans, null, lists/objects.

    Object keys sorted by Unicode code point; UTF-8, no ASCII escaping or whitespace.
    Floats are rejected. This is an explicit portable profile, not a claim of RFC 8785.
    """
    def check(node):
        if isinstance(node, dict):
            if any(not isinstance(key, str) for key in node):
                raise ValueError("JSON object keys must be strings")
            for child in node.values():
                check(child)
        elif isinstance(node, list):
            for child in node:
                check(child)
        elif node is not None and type(node) not in (str, int, bool):
            raise ValueError("Only integer JSON numbers are allowed in hashed contracts")
    check(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def content_hash(value):
    """Hash the whole document except its top-level content_hash member."""
    return hashlib.sha256(canonical_bytes({k: v for k, v in value.items() if k != "content_hash"})).hexdigest()


class ContractStore:
    def __init__(self, root: Path):
        missing_formats = {"uuid", "date-time"} - set(FormatChecker.checkers)
        if missing_formats:
            raise RuntimeError("Required format validators unavailable: " + ", ".join(sorted(missing_formats)))
        self.schemas = {}
        for path in sorted((root / "contracts").rglob("*.schema.json")):
            schema = json.loads(path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            if schema["$id"] in self.schemas:
                raise ValueError("Duplicate schema ID")
            self.schemas[schema["$id"]] = schema
        # No remote retrieval callback: unresolved references fail closed, never fetch.
        self.registry = Registry().with_resources((key, Resource.from_contents(value)) for key, value in self.schemas.items())

    def validate(self, name, value):
        key = name if name.startswith("https:") else "https://contracts.ecos.invalid/v1/" + name + ".schema.json"
        Draft202012Validator(self.schemas[key], registry=self.registry,
                            format_checker=FormatChecker()).validate(value)

    def check_references(self):
        def walk(node):
            if isinstance(node, dict):
                if "$ref" in node:
                    yield node["$ref"]
                for child in node.values():
                    yield from walk(child)
            elif isinstance(node, list):
                for child in node:
                    yield from walk(child)
        for schema in self.schemas.values():
            resolver = self.registry.resolver(schema["$id"])
            for reference in walk(schema):
                resolver.lookup(reference)
