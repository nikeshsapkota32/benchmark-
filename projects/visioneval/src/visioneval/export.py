"""Export validated evaluations to BenchGuard's saved-run schema."""

import hashlib
import json

from . import evaluate


def _ground_truth_sha256(data):
    """Fingerprint validated labels and their ID association, independent of order."""
    records = []
    for row in sorted(data["records"], key=lambda row: row["id"]):
        record = {"id": row["id"], "target": row["target"]}
        if data["kind"] == "arithmetic":
            # Hex avoids Python's decimal string conversion limit for large ints.
            record.update(target=hex(row["target"]), operator=row["operator"],
                          operands=[hex(value) for value in row["operands"]])
        records.append(record)
    payload = json.dumps({"schema_version": 1, "kind": data["kind"], "records": records},
                         sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def to_benchguard(data, *, response_policy="strict"):
    """Score all records, then export aggregate metrics and raw stable IDs."""
    report = evaluate(data, response_policy=response_policy)
    protocol = json.dumps({"export": "visioneval-benchguard-v2",
                           "kind": report["kind"], "protocol": report["protocol"],
                           "response_policy": response_policy,
                           "ground_truth_sha256": _ground_truth_sha256(data)},
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
