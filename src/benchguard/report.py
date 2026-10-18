"""Deterministic reports for already-validated comparisons."""

from dataclasses import asdict
import string

from .core import failed


def build_json_audit(baseline, candidate, rows, source_hashes, tolerance,
                     metric_tolerances, metric_directions):
    """Build a versioned audit envelope without input paths or raw sample IDs."""
    return {
        "schema_version": 1,
        "report_type": "benchguard-comparison",
        "passed": not failed(rows),
        "results": [asdict(row) for row in rows],
        "runs": {label: {field: data[field] for field in ("model", "dataset_revision", "protocol")}
                 for label, data in (("baseline", baseline), ("candidate", candidate))},
        "policy": {"tolerance": tolerance,
                   "metric_tolerances": dict(sorted(metric_tolerances.items())),
                   "metric_directions": dict(sorted(metric_directions.items()))},
        "source_sha256": {label.replace(" ", "_"): source_hashes[label]
                          for label in sorted(source_hashes)},
    }


def _cell(value):
    if value is None:
        return "—"
    # Numeric entities prevent input text from creating table cells, HTML,
    # links, emphasis, code spans or mentions in rendered Markdown.
    return "".join(" " if char.isspace() else f"&#92;u{ord(char):04x}"
                   if ord(char) < 32 or ord(char) == 127 or 0xD800 <= ord(char) <= 0xDFFF
                   else f"&#{ord(char)};"
                   if char in string.punctuation else char for char in str(value))


def render_markdown(baseline, candidate, rows, source_hashes, tolerance):
    lines = ["# BenchGuard comparison", "", f"Result: {'FAIL' if failed(rows) else 'PASS'}", "",
             "## Run metadata", "", "| Field | Baseline | Candidate |", "| --- | --- | --- |"]
    for field in ("model", "dataset_revision", "protocol"):
        lines.append("| " + " | ".join(_cell(value) for value in
                                      (field, baseline[field], candidate[field])) + " |")
    lines.extend(["", "## Metric results", "",
                  "| Task | Metric | Baseline | Candidate | Status | Reason |",
                  "| --- | --- | --- | --- | --- | --- |"])
    for row in rows:
        lines.append("| " + " | ".join(_cell(value) for value in
                     (row.task, row.metric, row.baseline, row.candidate, row.status, row.reason)) + " |")
    lines.extend(["", f"Default absolute tolerance: {_cell(tolerance)}", "",
                  "Per-metric overrides, when present, are reflected in each comparable result's reason.",
                  "", "## Input audit", "", "| Input | SHA-256 |", "| --- | --- |"])
    for label in sorted(source_hashes):
        lines.append(f"| {_cell(label)} | {_cell(source_hashes[label])} |")
    lines.extend(["", "Hashes identify the exact bytes read; they do not verify provenance or model quality."])
    return "\n".join(lines)
