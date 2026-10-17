"""Check whether saved reports describe the same measurement settings."""

from .configuration import CONFIGURATION_FIELDS
from .report import validate_report


def check_compatibility(baseline, candidate, *, required_fields=()):
    """Validate both reports, then return deterministic metadata differences."""
    if not isinstance(required_fields, (list, tuple)) or any(
            not isinstance(field, str) or field not in CONFIGURATION_FIELDS for field in required_fields):
        raise ValueError("required_fields must be a list or tuple of supported configuration field names")
    required = set(required_fields) | {"protocol"}
    validate_report(baseline)
    validate_report(candidate)
    differences = []

    def check(field, left, right, left_missing=False, right_missing=False):
        if left_missing or right_missing:
            missing = "both" if left_missing and right_missing else "baseline" if left_missing else "candidate"
            differences.append({"field": field, "reason": f"missing_in_{missing}"})
        elif left != right:
            differences.append({"field": field, "reason": "different"})

    for field in ("workload", "warmups", "repeats"):
        check(field, baseline[field], candidate[field])
    for field in ("system", "release", "machine", "python"):
        left, right = baseline["environment"][field], candidate["environment"][field]
        check("environment." + field, left, right, not left.strip(), not right.strip())
    before, after = baseline.get("configuration", {}), candidate.get("configuration", {})
    for field in sorted(required | before.keys() | after.keys()):
        check("configuration." + field, before.get(field), after.get(field),
              field not in before, field not in after)
    return {"schema_version": 1, "policy": "strict-metadata-v1", "compatible": not differences,
            "required_fields": sorted(required), "differences": differences}
