"""Read strict UTF-8 JSONL without materializing all input records."""

from contextlib import ExitStack
import json
from pathlib import Path

from . import _inspect, _validate_fields, _validate_splits


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("nonfinite JSON number")


def _records(stream, path):
    for line_number, raw in enumerate(stream, 1):
        try:
            line = raw.decode("utf-8")
            if not line.strip():
                raise ValueError("blank JSONL line")
            row = json.loads(line, object_pairs_hook=unique_object,
                             parse_constant=_reject_constant)
        except (UnicodeError, ValueError) as exc:
            # Avoid reproducing raw records in diagnostics.
            reason = "invalid UTF-8" if isinstance(exc, UnicodeError) else (
                "invalid JSON" if isinstance(exc, json.JSONDecodeError) else str(exc))
            raise ValueError(f"{path}:{line_number}: {reason}") from None
        yield row


def inspect_jsonl(splits, *, id_field="id", text_field="text"):
    """Map split names to paths; return findings only after every file validates."""
    _validate_fields(id_field, text_field)
    _validate_splits(splits)
    try:
        paths = {name: Path(path) for name, path in splits.items()}
    except TypeError:
        raise ValueError("split paths must be strings or path-like objects") from None
    with ExitStack() as stack:
        streams = {name: _records(stack.enter_context(paths[name].open("rb")), str(paths[name]))
                   for name in sorted(paths)}
        return _inspect(streams, sources={name: str(path) for name, path in paths.items()},
                        id_field=id_field, text_field=text_field)
