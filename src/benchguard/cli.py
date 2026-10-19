import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

from .core import compare, failed
from .report import build_json_audit, render_markdown


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate JSON key: {key}")
        obj[key] = value
    return obj


def load(path):
    return _load_with_digest(path)[0]


def _load_with_digest(path):
    content = Path(path).read_bytes()
    try:
        data = json.loads(content.decode("utf-8"), object_pairs_hook=_unique_object)
    except RecursionError:
        raise ValueError("JSON nesting exceeds parser limit") from None
    return data, hashlib.sha256(content).hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compare two AI benchmark runs offline")
    parser.add_argument("baseline")
    parser.add_argument("candidate")
    parser.add_argument("--tolerance", type=float, default=0.0,
                        help="allowed degradation in absolute metric units")
    parser.add_argument("--metric-tolerances", metavar="PATH",
                        help="JSON object mapping baseline metric names to absolute tolerances")
    parser.add_argument("--metric-directions", metavar="PATH",
                        help="JSON object mapping baseline metric names to required higher_is_better booleans")
    parser.add_argument("--format", choices=("json", "json-audit", "markdown"), default="json",
                        help="output format (default: json)")
    args = parser.parse_args(argv)
    try:
        source_hashes = {}
        overrides = {}
        directions = {}
        if args.metric_directions:
            directions, source_hashes["metric directions"] = _load_with_digest(args.metric_directions)
        if not isinstance(directions, dict):
            raise ValueError("metric directions file must contain a JSON object")
        if args.metric_tolerances:
            overrides, source_hashes["metric tolerances"] = _load_with_digest(args.metric_tolerances)
        if not isinstance(overrides, dict):
            raise ValueError("metric tolerances file must contain a JSON object")
        baseline, source_hashes["baseline"] = _load_with_digest(args.baseline)
        candidate, source_hashes["candidate"] = _load_with_digest(args.candidate)
        rows = compare(baseline, candidate, args.tolerance, metric_tolerances=overrides,
                       metric_directions=directions)
    except (ValueError, OSError, UnicodeError) as exc:
        print(f"benchguard: {exc}", file=sys.stderr)
        return 2
    if args.format == "markdown":
        print(render_markdown(baseline, candidate, rows, source_hashes, args.tolerance))
    else:
        if args.format == "json-audit":
            report = build_json_audit(baseline, candidate, rows, source_hashes, args.tolerance,
                                      overrides, directions)
        else:
            report = {"passed": not failed(rows), "results": [asdict(row) for row in rows]}
        print(json.dumps(report, indent=2, allow_nan=False))
    return 1 if failed(rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
