"""Validation is deliberately strict: incomplete runs must not pass CI."""

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Result:
    task: str
    metric: str
    baseline: float | None
    candidate: float | None
    status: str
    reason: str


def number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite number")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        raise ValueError(f"{label} must fit within the finite float range") from None
    if not finite:
        raise ValueError(f"{label} must be a finite number")
    return value


def validate(run):
    if (not isinstance(run, dict) or type(run.get("schema_version")) is not int
            or run["schema_version"] != 1):
        raise ValueError("schema_version must be 1")
    for field in ("model", "dataset_revision", "protocol"):
        if not isinstance(run.get(field), str) or not run[field].strip():
            raise ValueError(f"{field} must be a nonempty string")
    if not isinstance(run.get("results"), list) or not run["results"]:
        raise ValueError("results must be a nonempty list")
    indexed = {}
    for entry in run["results"]:
        if not isinstance(entry, dict):
            raise ValueError("each result must be an object")
        for field in ("task", "metric"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                raise ValueError(f"{field} must be a nonempty string")
        key = (entry["task"], entry["metric"])
        if key in indexed:
            raise ValueError(f"duplicate task/metric: {key}")
        number(entry.get("value"), "value")
        n = entry.get("samples")
        if isinstance(n, bool) or not isinstance(n, int) or n <= 0:
            raise ValueError("samples must be a positive integer")
        if type(entry.get("higher_is_better")) is not bool:
            raise ValueError("higher_is_better must be a boolean")
        indexed[key] = entry
    return indexed


def compare(baseline, candidate, tolerance=0.0, *, metric_tolerances=None):
    """Compare in native metric units; this is not a significance test.

    Model identifiers may differ. Protocol, dataset revision, sample counts
    and metric directions must match for a result to be comparable.
    Metric-specific absolute tolerances override the default across all tasks
    using that metric. Unknown baseline metrics are errors, not ignored rules.
    """
    number(tolerance, "tolerance")
    if tolerance < 0:
        raise ValueError("tolerance must be nonnegative")
    before, after = validate(baseline), validate(candidate)
    overrides = {} if metric_tolerances is None else metric_tolerances
    if not isinstance(overrides, dict):
        raise ValueError("metric_tolerances must be an object")
    baseline_metrics = {metric for _, metric in before}
    for metric, limit in overrides.items():
        if not isinstance(metric, str) or not metric.strip():
            raise ValueError("metric tolerance names must be nonempty strings")
        if metric not in baseline_metrics:
            raise ValueError(f"unknown baseline metric in tolerances: {metric}")
        number(limit, f"tolerance for {metric}")
        if limit < 0:
            raise ValueError(f"tolerance for {metric} must be nonnegative")
    for field in ("dataset_revision", "protocol"):
        if baseline[field] != candidate[field]:
            raise ValueError(f"incompatible {field}")
    rows = []
    for task, metric in sorted(before.keys() | after.keys()):
        a, b = before.get((task, metric)), after.get((task, metric))
        if a is None:
            status, reason = "added", "not present in baseline"
        elif b is None:
            status, reason = "missing", "required baseline result is absent"
        elif a["samples"] != b["samples"]:
            status, reason = "incompatible", "sample counts differ"
        elif a["higher_is_better"] != b["higher_is_better"]:
            status, reason = "incompatible", "metric direction differs"
        else:
            limit = overrides.get(metric, tolerance)
            degradation = (a["value"] - b["value"]) * (1 if a["higher_is_better"] else -1)
            regressed = degradation > limit and not math.isclose(
                degradation, limit, rel_tol=1e-12, abs_tol=1e-15
            )
            status = "regression" if regressed else "pass"
            reason = f"allowed absolute degradation: {limit:g}"
        rows.append(Result(task, metric, a["value"] if a else None,
                           b["value"] if b else None, status, reason))
    return rows


def failed(rows):
    return any(row.status in {"missing", "incompatible", "regression"} for row in rows)
