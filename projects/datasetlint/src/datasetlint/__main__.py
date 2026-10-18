import argparse
import json
from pathlib import Path
import sys

from . import TEXT_POLICIES, inspect
from .jsonl import inspect_jsonl, unique_object, _reject_constant
from .indexes import INDEX_BACKENDS


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check exact dataset duplicates and split overlap offline.")
    parser.add_argument("dataset", type=Path, nargs="?")
    parser.add_argument("--split", action="append", metavar="NAME=PATH",
                        help="read one JSONL file per named split; repeat for multiple splits")
    parser.add_argument("--id-field", default="id", help="top-level record key for IDs (default: id)")
    parser.add_argument("--text-field", default="text", help="top-level record key for text (default: text)")
    parser.add_argument("--text-policy", choices=TEXT_POLICIES, default="exact",
                        help="text matching policy; IDs always match exactly (default: exact)")
    parser.add_argument("--max-findings", type=int, metavar="N",
                        help="retain at most N findings while scanning all records; 0 keeps only totals")
    parser.add_argument("--index-backend", choices=INDEX_BACKENDS, default="memory",
                        help="duplicate index storage; sqlite writes temporary dataset values to disk")
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
            report = inspect_jsonl(splits, id_field=args.id_field, text_field=args.text_field,
                                   text_policy=args.text_policy, max_findings=args.max_findings,
                                   index_backend=args.index_backend)
        else:
            dataset = json.loads(args.dataset.read_text(encoding="utf-8"),
                                 object_pairs_hook=unique_object, parse_constant=_reject_constant)
            report = inspect(dataset, id_field=args.id_field, text_field=args.text_field,
                             text_policy=args.text_policy, max_findings=args.max_findings,
                             index_backend=args.index_backend)
    except (OSError, ValueError) as exc:
        print(f"datasetlint: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
