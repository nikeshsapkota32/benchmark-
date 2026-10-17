import argparse
import hashlib
import json
import platform
import sys

from . import benchmark


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run a synthetic CPU timing demo on this host.")
    parser.add_argument("--demo", action="store_true", required=True,
                        help="measure SHA-256 of 1 MiB; this is not model inference")
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--repeats", type=int, default=10)
    args = parser.parse_args(argv)
    payload = b"x" * (1024 * 1024)
    try:
        report = benchmark(lambda: hashlib.sha256(payload).digest(),
                           workload="synthetic SHA-256 of 1 MiB; not model inference",
                           warmups=args.warmups, repeats=args.repeats,
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
