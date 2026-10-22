"""Read the explicit digits-csv-v1 layout without inferring types or dialects."""

import csv
from pathlib import Path


_FIELDS = ("id", "target", "prediction")


def load_digits_csv(path, *, model, dataset_revision, protocol):
    """Build evaluator input; the existing evaluator validates record semantics."""
    records = []
    try:
        with Path(path).open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.reader(stream, delimiter=",", quotechar='"',
                                doublequote=True, escapechar=None,
                                skipinitialspace=False, quoting=csv.QUOTE_MINIMAL,
                                strict=True)
            header = next(reader, None)
            if header != list(_FIELDS):
                raise ValueError("CSV header must be exactly id,target,prediction")
            for row in reader:
                if len(row) != len(_FIELDS):
                    raise ValueError(f"CSV record ending at physical line {reader.line_num} "
                                     "must contain exactly 3 fields")
                records.append(dict(zip(_FIELDS, row)))
    except csv.Error:
        raise ValueError(f"invalid CSV near physical line {reader.line_num}") from None
    if not records:
        raise ValueError("CSV needs at least one prediction record")
    return {"schema_version": 1, "kind": "digits", "model": model,
            "dataset_revision": dataset_revision, "protocol": protocol,
            "records": records}
