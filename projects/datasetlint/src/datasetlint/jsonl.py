"""Read strict UTF-8 JSONL without materializing all input records."""

from contextlib import ExitStack, closing
import hashlib
import json
from pathlib import Path

from . import _inspect, _validate_fields, _validate_splits, _validate_text_policy, _validate_max_findings
from .indexes import validate_backend


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("nonfinite JSON number")


def _loads(payload):
    try:
        return json.loads(payload, object_pairs_hook=unique_object,
                          parse_constant=_reject_constant)
    except RecursionError:
        # Keep parser resource failures within the normal input-error contract.
        # Do not change the process recursion limit or expose decoder details.
        raise ValueError("JSON nesting exceeds parser limit") from None


def _records(stream, path, digest=None):
    for line_number, raw in enumerate(stream, 1):
        if digest is not None:
            digest.update(raw)
        try:
            line = raw.decode("utf-8")
            if not line.strip():
                raise ValueError("blank JSONL line")
            row = _loads(line)
        except (UnicodeError, ValueError) as exc:
            # Avoid reproducing raw records in diagnostics.
            reason = "invalid UTF-8" if isinstance(exc, UnicodeError) else (
                "invalid JSON" if isinstance(exc, json.JSONDecodeError) else str(exc))
            raise ValueError(f"{path}:{line_number}: {reason}") from None
        yield row


def _file_records(path, digest):
    # Opening is deferred until the scanner reaches this split. Normal
    # exhaustion closes the file before the next split starts; closing the
    # generator also closes it when record validation aborts outside _records.
    with path.open("rb") as stream:
        yield from _records(stream, str(path), digest)


def inspect_jsonl(splits, *, id_field="id", text_field="text", text_policy="exact", max_findings=None,
                  index_backend="memory"):
    """Map split names to paths; return findings only after every file validates."""
    _validate_fields(id_field, text_field)
    _validate_text_policy(text_policy)
    _validate_max_findings(max_findings)
    validate_backend(index_backend)
    _validate_splits(splits)
    try:
        paths = {name: Path(path) for name, path in splits.items()}
    except TypeError:
        raise ValueError("split paths must be strings or path-like objects") from None
    with ExitStack() as stack:
        digests = {name: hashlib.sha256() for name in sorted(paths)}
        streams = {name: stack.enter_context(closing(_file_records(paths[name], digests[name])))
                   for name in sorted(paths)}
        report = _inspect(streams, sources={name: str(path) for name, path in paths.items()},
                          id_field=id_field, text_field=text_field, text_policy=text_policy,
                          max_findings=max_findings, index_backend=index_backend)
        report["source_sha256"] = {name: digest.hexdigest() for name, digest in digests.items()}
        return report
