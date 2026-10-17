import argparse
import json
from pathlib import Path
import sys

from . import inspect
from .jsonl import inspect_jsonl, unique_object


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check exact dataset duplicates and split overlap offline.")
    parser.add_argument("dataset", type=Path, nargs="?")
    parser.add_argument("--split", action="append", metavar="NAME=PATH",
                        help="read one JSONL file per named split; repeat for multiple splits")
    parser.add_argument("--id-field", default="id", help="top-level record key for IDs (default: id)")
    parser.add_argument("--text-field", default="text", help="top-level record key for text (default: text)")
    args = parser.parse_args(argv)
    if (args.dataset is None) == (args.split is None):
        parser.error("provide either a JSON dataset or one or more --split NAME=PATH options")
    try:
        if args.split is not None:
            splits = {}
            for spec in args.split:
                name, separator, path = spec.partition("=")
                if not separator or not name.strip() or not path.strip():
                    raise ValueError("--split requires nonempty NAME=PATH")
                if name in splits:
                    raise ValueError("duplicate split name")
                splits[name] = path
            report = inspect_jsonl(splits, id_field=args.id_field, text_field=args.text_field)
        else:
            dataset = json.loads(args.dataset.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
            report = inspect(dataset, id_field=args.id_field, text_field=args.text_field)
    except (OSError, ValueError) as exc:
        print(f"datasetlint: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
