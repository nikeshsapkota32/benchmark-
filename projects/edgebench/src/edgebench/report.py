"""Validate saved timing reports, without executing a workload."""

import math
import statistics

from .configuration import snapshot


def summarize(durations):
    ordered = sorted(durations)
    count = len(ordered)
    middle = count // 2
    # A mean of the middle pair avoids overflowing their sum.
    median = ordered[middle] if count % 2 else statistics.mean(ordered[middle - 1:middle + 1])
    return {"min": ordered[0], "max": ordered[-1],
            "mean": statistics.mean(durations), "median": median,
            "p90": ordered[(90 * count + 99) // 100 - 1],
            "p95": ordered[(95 * count + 99) // 100 - 1]}


def _number(value, where):
    if type(value) not in (int, float):
        raise ValueError(f"{where} must be a finite nonnegative number")
    try:
        valid = math.isfinite(value) and value >= 0
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f"{where} must be a finite nonnegative number")


def validate_report(report):
    """Return None on success; raise ValueError on invalid or inconsistent data."""
    if not isinstance(report, dict) or type(report.get("schema_version")) is not int or report["schema_version"] != 1:
        raise ValueError("schema_version must be integer 1")
    if not isinstance(report.get("workload"), str) or not report["workload"].strip():
        raise ValueError("workload must be a nonempty description")
    for key, minimum in (("warmups", 0), ("repeats", 1)):
        if type(report.get(key)) is not int or report[key] < minimum:
            raise ValueError(f"{key} must be an integer >= {minimum}")
    if report.get("unit") != "ms" or report.get("percentile_method") != "nearest_rank":
        raise ValueError("unit must be ms and percentile_method must be nearest_rank")
    environment = report.get("environment")
    if not isinstance(environment, dict) or any(
            not isinstance(environment.get(key), str) for key in ("system", "release", "machine", "python")):
        raise ValueError("environment must contain system, release, machine and python strings")
    # Early schema-v1 reports predate configuration snapshots.
    if "configuration" in report:
        if not isinstance(report["configuration"], dict):
            raise ValueError("configuration must be an object")
        snapshot(report["configuration"])
    durations = report.get("durations")
    if not isinstance(durations, list) or len(durations) != report["repeats"]:
        raise ValueError("durations must be a list with exactly repeats entries")
    for index, value in enumerate(durations):
        _number(value, f"durations[{index}]")
    summary = report.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("summary must be an object")
    for key, expected in summarize(durations).items():
        actual = summary.get(key)
        _number(actual, f"summary.{key}")
        matches = math.isclose(actual, expected, rel_tol=1e-12, abs_tol=0) if key in ("mean", "median") else actual == expected
        if not matches:
            raise ValueError(f"summary.{key} does not match durations")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("nonfinite JSON number")
