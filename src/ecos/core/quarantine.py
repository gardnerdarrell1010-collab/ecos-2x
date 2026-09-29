"""Classify synthetic/source extracts without promoting or repairing them."""
from collections import Counter


def classify_rows(rows, expected_columns, required_types):
    identifiers = Counter(row.get("legacy_id") for row in rows if row.get("legacy_id"))
    results = []
    seen_locators = set()
    for row in rows:
        locator = (row["batch_id"], row["source_locator"])
        if locator in seen_locators:
            raise ValueError("Duplicate immutable source locator")
        seen_locators.add(locator)
        reasons = []
        if list(row["values"]) != expected_columns:
            reasons.append("column_drift")
        if not row.get("legacy_id"):
            reasons.append("missing_legacy_id")
        elif identifiers[row["legacy_id"]] > 1:
            reasons.append("duplicate_legacy_id")
        for name, expected_type in required_types.items():
            if type(row["values"].get(name)) is not expected_type:
                reasons.append("invalid_type." + name)
        state = "identity_unresolved" if reasons == ["duplicate_legacy_id"] else "invalid" if reasons else "validated"
        results.append({"locator": locator, "state": state, "reason_codes": reasons})
    return results
