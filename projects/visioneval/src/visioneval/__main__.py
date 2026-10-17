import argparse
import json
from pathlib import Path
import sys

from . import evaluate


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Score saved digit or arithmetic predictions offline.")
    parser.add_argument("predictions", type=Path)
    parser.add_argument("--details", action="store_true",
                        help="include per-record indices and outcomes, without raw answers or IDs")
    args = parser.parse_args(argv)
    try:
        report = evaluate(json.loads(args.predictions.read_text(encoding="utf-8"),
                                     object_pairs_hook=unique_object), include_details=args.details)
    except (OSError, ValueError) as exc:
        print(f"visioneval: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
