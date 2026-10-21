"""Dependency-free linear inference example; bundled weights are synthetic/untrained.

Run from the EdgeBench project checkout after installing edgebench. File loading,
validation, float conversion and hashing happen before benchmark() is called.
"""

import argparse
import json
import math
from pathlib import Path
import platform
import sys

from edgebench import benchmark
from edgebench._linear_fixture import load_fixture


def load_workload(model_path, input_path):
    """Load a dense linear classifier and fixed vector; return callable + metadata."""
    weights, bias, values, configuration = load_fixture(model_path, input_path)

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

    configuration.update({
        "runtime": "Python/stdlib-linear-v1",
        "runtime_version": platform.python_implementation() + " " + platform.python_version(),
        "device": "cpu", "dtype": "Python float",
        "protocol": "linear-argmax-v1; row-major sequential sum; first-index ties; "
                    "logit allocation and finiteness check included; loading/validation/hashing excluded",
    })
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
