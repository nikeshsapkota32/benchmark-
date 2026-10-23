"""Check whether saved reports describe the same measurement settings."""

from .configuration import CONFIGURATION_FIELDS
from .report import validate_report


def check_compatibility(baseline, candidate, *, required_fields=(), vary_fields=()):
    """Validate both reports, then return deterministic metadata differences."""
    if not isinstance(required_fields, (list, tuple)) or any(
            not isinstance(field, str) or field not in CONFIGURATION_FIELDS for field in required_fields):
        raise ValueError("required_fields must be a list or tuple of supported configuration field names")
    if not isinstance(vary_fields, (list, tuple)) or any(
            not isinstance(field, str) or field not in CONFIGURATION_FIELDS - {"protocol"}
            for field in vary_fields):
        raise ValueError("vary_fields must be a list or tuple of supported configuration field names other than protocol")
    varying = set(vary_fields)
    required = set(required_fields) | varying | {"protocol"}
    validate_report(baseline)
    validate_report(candidate)
    differences = []
    permitted = []

    def check(field, left, right, left_missing=False, right_missing=False, allow_difference=False):
        if left_missing or right_missing:
            missing = "both" if left_missing and right_missing else "baseline" if left_missing else "candidate"
            differences.append({"field": field, "reason": f"missing_in_{missing}"})
        elif left != right:
            target = permitted if allow_difference else differences
            target.append({"field": field, "reason": "different"})

    for field in ("workload", "warmups", "repeats"):
        check(field, baseline[field], candidate[field])
    for field in ("system", "release", "machine", "python"):
        left, right = baseline["environment"][field], candidate["environment"][field]
        check("environment." + field, left, right, not left.strip(), not right.strip())
    before, after = baseline.get("configuration", {}), candidate.get("configuration", {})
    for field in sorted(required | before.keys() | after.keys()):
        check("configuration." + field, before.get(field), after.get(field),
              field not in before, field not in after, allow_difference=field in varying)
    result = {"schema_version": 1, "policy": "strict-metadata-v1", "compatible": not differences,
              "required_fields": sorted(required), "differences": differences}
    if varying:
        result.update(policy="controlled-fields-v1", vary_fields=sorted(varying),
                      permitted_differences=permitted)
    return result
