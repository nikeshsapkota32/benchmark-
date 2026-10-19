"""Dependency-free linear inference example; bundled weights are synthetic/untrained.

Run from the EdgeBench project checkout after installing edgebench. File loading,
validation, float conversion and hashing happen before benchmark() is called.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import platform
import sys

from edgebench import benchmark
from edgebench.report import reject_constant, unique_object


def _load(path, fields):
    payload = path.read_bytes()
    try:
        data = json.loads(payload.decode("utf-8"), object_pairs_hook=unique_object,
                          parse_constant=reject_constant)
    except RecursionError:
        raise ValueError("JSON nesting exceeds parser limit") from None
    if not isinstance(data, dict) or set(data) != fields | {"schema_version"}:
        raise ValueError("unexpected or missing fixture fields")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("schema_version must be integer 1")
    return data, "sha256:" + hashlib.sha256(payload).hexdigest()


def _vector(values):
    if not isinstance(values, list) or not values:
        raise ValueError("vectors must be nonempty lists of finite numbers")
    converted = []
    for value in values:
        if type(value) not in (int, float):
            raise ValueError("vector entries must be finite numbers, not booleans")
        try:
            value = float(value)
        except OverflowError:
            raise ValueError("vector entry exceeds finite float range") from None
        if not math.isfinite(value):
            raise ValueError("vector entries must be finite numbers")
        converted.append(value)
    return tuple(converted)


def load_workload(model_path, input_path):
    """Load a dense linear classifier and fixed vector; return callable + metadata."""
    model, model_hash = _load(model_path, {"weights", "bias"})
    inputs, input_hash = _load(input_path, {"values"})
    if not isinstance(model["weights"], list) or not model["weights"]:
        raise ValueError("weights must be a nonempty list of row vectors")
    weights = tuple(_vector(row) for row in model["weights"])
    bias, values = _vector(model["bias"]), _vector(inputs["values"])
    if len(bias) != len(weights) or any(len(row) != len(values) for row in weights):
        raise ValueError("model and input dimensions do not match")

    def predict():
        # Row-major, sequential Python arithmetic, followed by first-index argmax.
        logits = []
        for row, offset in zip(weights, bias):
            total = 0.0
            for weight, value in zip(row, values):
                total += weight * value
            logits.append(total + offset)
        if not all(math.isfinite(logit) for logit in logits):
            raise ValueError("linear inference produced a nonfinite logit")
        return max(range(len(logits)), key=logits.__getitem__)

    configuration = {
        "model": "dense-linear-argmax", "model_revision": model_hash,
        "input_revision": input_hash, "input_shape": [len(values)], "batch_size": 1,
        "runtime": "Python/stdlib-linear-v1",
        "runtime_version": platform.python_implementation() + " " + platform.python_version(),
        "device": "cpu", "dtype": "Python float",
        "protocol": "linear-argmax-v1; row-major sequential sum; first-index ties; "
                    "logit allocation and finiteness check included; loading/validation/hashing excluded",
    }
    return predict, configuration


def main(argv=None):
    parser = argparse.ArgumentParser(description="Time local dense linear inference; no accuracy claim.")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--repeats", type=int, default=10)
    args = parser.parse_args(argv)
    try:
        operation, configuration = load_workload(args.model, args.input)
        report = benchmark(operation, workload="Python dense linear argmax; caller-supplied weights",
                           configuration=configuration, warmups=args.warmups, repeats=args.repeats)
    except (OSError, ValueError) as exc:
        print(f"linear-example: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
