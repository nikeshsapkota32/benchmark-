"""Describe saved latency changes only after checking measurement metadata."""

from .compatibility import check_compatibility
from .report import summarize


def compare_reports(baseline, candidate, *, required_fields=(), vary_fields=()):
    """Return descriptive millisecond deltas, not a performance pass/fail gate."""
    compatibility = check_compatibility(baseline, candidate,
                                        required_fields=required_fields, vary_fields=vary_fields)
    result = {"schema_version": 1, "report_type": "edgebench-comparison", "unit": "ms",
              "compatibility": compatibility, "metrics": []}
    if not compatibility["compatible"]:
        return result
    # Recompute instead of comparing summaries that may have been rounded
    # within the saved-report validator's accepted serialization tolerance.
    before, after = summarize(baseline["durations"]), summarize(candidate["durations"])
    result["metrics"] = [
        {"metric": name, "baseline": before[name], "candidate": after[name],
         "delta_ms": after[name] - before[name]}
        for name in ("min", "max", "mean", "median", "p90", "p95")
    ]
    return result
