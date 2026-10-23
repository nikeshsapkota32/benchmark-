"""Optional synchronous NumPy CPU example using synthetic, untrained fixtures."""

import argparse
import json
from pathlib import Path
import sys

from edgebench import benchmark
from edgebench._linear_fixture import load_fixture


def _dependencies():
    try:
        import numpy
        import threadpoolctl
    except ImportError as exc:
        raise ValueError("NumPy example requires the numpy-example extra: "
                         "python -m pip install '.[numpy-example]'") from exc
    return numpy, threadpoolctl


def _load_workload(np, model_path, input_path):
    weights, bias, values, configuration = load_fixture(model_path, input_path)
    weights, bias, values = (np.array(item, dtype=np.float64, order="C")
                             for item in (weights, bias, values))
    for array in (weights, bias, values):
        array.flags.writeable = False

    def predict():
        logits = weights @ values + bias
        if not np.isfinite(logits).all():
            raise ValueError("linear inference produced a nonfinite logit")
        return int(np.argmax(logits))

    configuration.update({
        "runtime": "NumPy/linear-v1", "device": "cpu", "dtype": "float64",
        "protocol": "numpy-linear-argmax-v1; C-contiguous float64 matvec then bias; "
                    "allocation, finiteness check and first-index argmax included; "
                    "loading/validation/conversion/hashing/thread setup excluded",
    })
    return predict, configuration


def _backends(threadpoolctl, threads):
    backends = [info for info in threadpoolctl.threadpool_info()
                if info.get("user_api") == "blas"]
    if not backends or any(type(info.get("num_threads")) is not int or
                           info["num_threads"] != threads for info in backends):
        raise ValueError("cannot verify the requested BLAS thread limit")
    if any(not isinstance(info.get("version"), str) or not info["version"].strip()
           for info in backends):
        raise ValueError("cannot identify the loaded BLAS version")
    # Deliberately exclude library file paths and other unrestricted native metadata.
    selected = [{key: info.get(key) for key in
                 ("internal_api", "version", "threading_layer", "architecture")}
                for info in backends]
    return sorted(selected, key=lambda item: json.dumps(item, sort_keys=True))


def run(model_path, input_path, *, threads=1, warmups=3, repeats=10):
    """Run in a dedicated process; native thread controls affect other callers."""
    if type(threads) is not int or threads < 1:
        raise ValueError("threads must be a positive integer")
    np, threadpoolctl = _dependencies()
    operation, configuration = _load_workload(np, model_path, input_path)
    with threadpoolctl.threadpool_limits(limits=threads, user_api="blas"):
        backends = _backends(threadpoolctl, threads)
        configuration["threads"] = threads
        # Schema-v1 runtime_version is a string. Canonical JSON preserves structured
        # native identities without extending the shared configuration schema.
        configuration["runtime_version"] = json.dumps({
            "numpy": np.__version__, "threadpoolctl": threadpoolctl.__version__,
            "blas": backends,
        }, sort_keys=True, separators=(",", ":"))
        with np.errstate(over="ignore", invalid="ignore"):
            report = benchmark(operation, workload="NumPy dense linear argmax; caller-supplied weights",
                               configuration=configuration, warmups=warmups, repeats=repeats)
        if _backends(threadpoolctl, threads) != backends:
            raise ValueError("loaded BLAS configuration changed during measurement")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description="Time synchronous NumPy CPU inference; no accuracy claim.")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--repeats", type=int, default=10)
    args = parser.parse_args(argv)
    try:
        report = run(args.model, args.input, threads=args.threads,
                     warmups=args.warmups, repeats=args.repeats)
    except (OSError, ValueError) as exc:
        print(f"numpy-linear-example: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
