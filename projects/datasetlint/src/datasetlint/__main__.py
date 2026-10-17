import argparse
import json
from pathlib import Path
import sys

from . import inspect


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check exact dataset duplicates and split overlap offline.")
    parser.add_argument("dataset", type=Path)
    args = parser.parse_args(argv)
    try:
        dataset = json.loads(args.dataset.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
        report = inspect(dataset)
    except (OSError, ValueError) as exc:
        print(f"datasetlint: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
