import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from .core import compare, failed


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate JSON key: {key}")
        obj[key] = value
    return obj


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_unique_object)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compare two AI benchmark runs offline")
    parser.add_argument("baseline")
    parser.add_argument("candidate")
    parser.add_argument("--tolerance", type=float, default=0.0,
                        help="allowed degradation in absolute metric units")
    args = parser.parse_args(argv)
    try:
        rows = compare(load(args.baseline), load(args.candidate), args.tolerance)
    except (ValueError, OSError, UnicodeError) as exc:
        print(f"benchguard: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"passed": not failed(rows), "results": [asdict(row) for row in rows]},
                     indent=2, allow_nan=False))
    return 1 if failed(rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
