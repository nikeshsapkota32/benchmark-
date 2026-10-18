"""Convert one lm-evaluation-harness aggregate metric to a BenchGuard run."""

import argparse
import json
import sys

from .cli import load
from .core import number, validate


_EVAL_SETTINGS = (
    "limit", "gen_kwargs", "random_seed", "numpy_seed", "torch_seed",
    "fewshot_seed",
)


def _mapping_at(export, field, task):
    mapping = export.get(field)
    if not isinstance(mapping, dict) or task not in mapping:
        raise ValueError(f"missing {field} for task {task}")
    return mapping[task]


def adapt(export, *, task, metric, model, dataset_revision, protocol):
    """Select an exact filtered metric from a complete aggregate export.

    `protocol` is caller-reviewed metadata for settings the harness export does
    not fully capture (such as dataset pinning and prompt/model invocation).
    """
    if not isinstance(export, dict):
        raise ValueError("harness export must be an object")
    for label, value in (("task", task), ("metric", metric), ("model", model),
                         ("dataset_revision", dataset_revision), ("protocol", protocol)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{label} must be a nonempty string")
    name, separator, filter_name = metric.rpartition(",")
    if not separator or not name or not filter_name:
        raise ValueError("metric must be an exact metric,filter key, e.g. acc,none")
    result = _mapping_at(export, "results", task)
    if not isinstance(result, dict) or metric not in result:
        raise ValueError(f"missing result for {task}/{metric}")
    score = number(result[metric], "metric value")
    counts = _mapping_at(export, "n-samples", task)
    if not isinstance(counts, dict):
        raise ValueError("n-samples entry must be an object")
    original, effective = counts.get("original"), counts.get("effective")
    if (type(original) is not int or original <= 0 or type(effective) is not int
            or effective <= 0 or effective > original):
        raise ValueError("n-samples must contain valid original/effective counts")
    if type(result.get("sample_len")) is not int or result["sample_len"] != effective:
        raise ValueError("sample_len must match effective sample count")
    directions = _mapping_at(export, "higher_is_better", task)
    if not isinstance(directions, dict) or type(directions.get(name)) is not bool:
        raise ValueError(f"missing unambiguous direction for {task}/{name}")
    version = _mapping_at(export, "versions", task)
    if (isinstance(version, bool) or not isinstance(version, (str, int, float))
            or not str(version).strip()):
        raise ValueError("task version must be specified")
    if isinstance(version, float):
        number(version, "task version")
    fewshot = _mapping_at(export, "n-shot", task)
    if type(fewshot) is not int or fewshot < 0:
        raise ValueError("n-shot must be a nonnegative integer")
    task_config = _mapping_at(export, "configs", task)
    if not isinstance(task_config, dict) or not task_config:
        raise ValueError("task config must be a nonempty object")
    harness_revision = export.get("git_hash")
    if not isinstance(harness_revision, str) or not harness_revision.strip():
        raise ValueError("git_hash must identify the harness revision")
    settings = export.get("config")
    if not isinstance(settings, dict) or any(key not in settings for key in _EVAL_SETTINGS):
        raise ValueError("config must contain the harness evaluation settings")
    task_hashes = export.get("task_hashes", {})
    if not isinstance(task_hashes, dict):
        raise ValueError("task_hashes must be an object when present")
    task_hash = task_hashes.get(task)
    if task_hash is not None and (not isinstance(task_hash, str) or not task_hash.strip()):
        raise ValueError("task hash must be a nonempty string when present")
    metadata = {
        "adapter": "benchguard-lmeval-v1", "caller_protocol": protocol,
        "harness_revision": harness_revision, "task": task, "task_version": version,
        "fewshot": fewshot, "filter": filter_name, "metric": name,
        "task_config": task_config, "original_samples": original,
        "task_hash": task_hash,
        "evaluation_settings": {key: settings[key] for key in _EVAL_SETTINGS},
    }
    try:
        pinned_protocol = json.dumps(metadata, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"non-JSON protocol metadata: {exc}") from exc
    run = {
        "schema_version": 1, "model": model, "dataset_revision": dataset_revision,
        "protocol": pinned_protocol,
        "results": [{"task": task, "metric": metric, "value": score,
                     "samples": effective, "higher_is_better": directions[name]}],
    }
    validate(run)
    return run


def main(argv=None):
    parser = argparse.ArgumentParser(description="Convert one lm-evaluation-harness metric offline")
    parser.add_argument("export", help="saved aggregate results JSON")
    parser.add_argument("--task", required=True)
    parser.add_argument("--metric", required=True, help="exact metric,filter key, e.g. acc,none")
    parser.add_argument("--model", required=True, help="explicit model revision label")
    parser.add_argument("--dataset-revision", required=True, help="pinned dataset revision")
    parser.add_argument("--protocol", required=True, help="reviewed extra protocol metadata")
    args = parser.parse_args(argv)
    try:
        run = adapt(load(args.export), task=args.task, metric=args.metric,
                    model=args.model, dataset_revision=args.dataset_revision,
                    protocol=args.protocol)
    except (ValueError, OSError, UnicodeError) as exc:
        print(f"benchguard-lmeval: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(run, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
