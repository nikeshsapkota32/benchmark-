import argparse
import hashlib
import json
import platform
from pathlib import Path
import sys

from . import benchmark, validate_report
from .report import reject_constant, unique_object


def main(argv=None):
    parser = argparse.ArgumentParser(description="Measure a synthetic CPU workload or validate a saved report offline.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--demo", action="store_true",
                        help="measure SHA-256 of 1 MiB; this is not model inference")
    mode.add_argument("--validate", type=Path, metavar="REPORT", help="check a saved JSON report without running a workload")
    parser.add_argument("--warmups", type=int)
    parser.add_argument("--repeats", type=int)
    args = parser.parse_args(argv)
    if args.validate is not None:
        if args.warmups is not None or args.repeats is not None:
            parser.error("--warmups and --repeats require --demo")
        try:
            report = json.loads(args.validate.read_text(encoding="utf-8"),
                                object_pairs_hook=unique_object, parse_constant=reject_constant)
            validate_report(report)
        except (OSError, ValueError) as exc:
            print(f"edgebench: {exc}", file=sys.stderr)
            return 2
        print(json.dumps({"valid": True, "schema_version": 1, "repeats": report["repeats"]}))
        return 0
    payload = b"x" * (1024 * 1024)
    try:
        report = benchmark(lambda: hashlib.sha256(payload).digest(),
                           workload="synthetic SHA-256 of 1 MiB; not model inference",
                           warmups=3 if args.warmups is None else args.warmups,
                           repeats=10 if args.repeats is None else args.repeats,
                           configuration={"runtime": "Python/hashlib",
                                          "runtime_version": platform.python_version(),
                                          "device": "cpu", "dtype": "bytes",
                                          "input_shape": [len(payload)],
                                          "protocol": "SHA-256; fixed x bytes; payload allocated before timing"})
    except ValueError as exc:
        print(f"edgebench: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
