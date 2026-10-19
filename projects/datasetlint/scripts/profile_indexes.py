"""Linux-only, synthetic resource characterization; no performance pass/fail gate."""

import argparse
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import subprocess
import sys
import tempfile
import time

import datasetlint
from datasetlint import indexes, jsonl


def write_synthetic(directory, records, text_bytes):
    """Stream unique train records and every tenth train record into a test split."""
    if type(records) is not int or records < 10:
        raise ValueError("records must be an integer >= 10")
    if type(text_bytes) is not int or text_bytes < 32:
        raise ValueError("text_bytes must be an integer >= 32")
    paths = {name: Path(directory) / (name + ".jsonl") for name in ("train", "test")}
    with paths["train"].open("wb") as train, paths["test"].open("wb") as test:
        for index in range(records):
            prefix = f"synthetic-{index:012d}:"
            text = prefix + "x" * (text_bytes - len(prefix))
            row = {"id": f"synthetic-{index}", "text": text}
            raw = (json.dumps(row, separators=(",", ":")) + "\n").encode("ascii")
            train.write(raw)
            if index % 10 == 0:
                test.write(raw)
    return paths


def measure(paths, backend):
    # ru_maxrss units are KiB on Linux, unlike macOS. Do not guess elsewhere.
    if sys.platform != "linux":
        raise ValueError("resource profiling currently supports Linux only")
    import resource
    before = resource.getrusage(resource.RUSAGE_SELF)
    started = time.perf_counter()
    report = jsonl.inspect_jsonl(paths, index_backend=backend, max_findings=0)
    elapsed = time.perf_counter() - started
    after = resource.getrusage(resource.RUSAGE_SELF)
    peak = after.ru_maxrss * 1024
    return {"backend": backend, "elapsed_seconds": elapsed, "peak_rss_bytes": peak,
            "filesystem_operations": {"input": after.ru_inblock - before.ru_inblock,
                                      "output": after.ru_oublock - before.ru_oublock},
            "report": report}


def profile(records=10000, text_bytes=512, trials=3):
    if sys.platform != "linux":
        raise ValueError("resource profiling currently supports Linux only")
    if type(trials) is not int or trials < 1:
        raise ValueError("trials must be a positive integer")
    runs, reference = [], None
    with tempfile.TemporaryDirectory(prefix="datasetlint-profile-") as directory:
        paths = write_synthetic(directory, records, text_bytes)
        input_bytes = {name: path.stat().st_size for name, path in paths.items()}
        for trial in range(trials):
            # Alternate first backend; OS caches are intentionally not flushed.
            for backend in (("memory", "sqlite") if trial % 2 == 0 else ("sqlite", "memory")):
                completed = subprocess.run(
                    [sys.executable, str(Path(__file__).resolve()), "--worker", backend,
                     str(paths["train"]), str(paths["test"])],
                    check=False, capture_output=True, text=True, timeout=300)
                if completed.returncode:
                    raise ValueError(f"{backend} profiling worker failed (exit {completed.returncode})")
                result = json.loads(completed.stdout)
                report = result.pop("report")
                if reference is not None and report != reference:
                    raise ValueError("backend reports differ; resource results discarded")
                reference = report
                result["trial"] = trial + 1
                runs.append(result)
        expected_test = (records + 9) // 10
        if (reference["counts"] != {"train": records, "test": expected_test}
                or reference["total_findings"] != expected_test * 2 or reference["passed"]
                or reference["findings"] or not reference["findings_truncated"]):
            raise ValueError("unexpected synthetic validation result; resource results discarded")
    source_hashes = {module.__name__: hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
                     for module in (datasetlint, indexes, jsonl)}
    return {"schema_version": 1, "experiment": "datasetlint-synthetic-index-profile-v1",
            "environment": {"system": platform.system(), "release": platform.release(),
                            "machine": platform.machine(), "python": platform.python_version(),
                            "sqlite": sqlite3.sqlite_version},
            "workload": {"unique_train_records": records, "test_records": expected_test,
                         "test_selection": "every tenth train record, starting at zero",
                         "text_bytes": text_bytes, "max_findings": 0, "input_bytes": input_bytes},
            "measurement": {"time": "perf_counter around inspect_jsonl; excludes interpreter startup and input generation",
                            "memory": "Linux process-lifetime ru_maxrss in bytes; includes interpreter and imports",
                            "io": "Linux RUSAGE_SELF ru_inblock/ru_oublock deltas around inspect_jsonl including cleanup; filesystem operation counters, not bytes or syscall counts",
                            "storage": "Python tempfile default; filesystem and OS caches not characterized",
                            "order": "alternating first backend; fresh process per run; no cache flushing"},
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "implementation_sha256": source_hashes,
            "validation_report": reference, "runs": runs}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=int, default=10000)
    parser.add_argument("--text-bytes", type=int, default=512)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--worker", nargs=3, metavar=("BACKEND", "TRAIN", "TEST"), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.worker:
            backend, train, test = args.worker
            result = measure({"train": train, "test": test}, backend)
        else:
            result = profile(args.records, args.text_bytes, args.trials)
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"profile_indexes: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
