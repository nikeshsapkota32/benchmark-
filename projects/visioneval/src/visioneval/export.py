"""Export validated evaluations to BenchGuard's saved-run schema."""

import json

from . import evaluate


def to_benchguard(data, *, response_policy="strict"):
    """Score all records, then export aggregate metrics and raw stable IDs."""
    report = evaluate(data, response_policy=response_policy)
    protocol = json.dumps({"export": "visioneval-benchguard-v1",
                           "kind": report["kind"], "protocol": report["protocol"],
                           "response_policy": response_policy},
                          sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    metrics = [("exact_match", True)]
    if report["kind"] == "digits":
        metrics.append(("character_error_rate", False))
    return {"schema_version": 1, "model": report["model"],
            "dataset_revision": report["dataset_revision"], "protocol": protocol,
            "results": [{"task": "visioneval/" + report["kind"], "metric": metric,
                         "value": report[metric], "higher_is_better": direction,
                         "samples": report["samples"],
                         "sample_ids": [row["id"] for row in data["records"]]}
                        for metric, direction in metrics]}
