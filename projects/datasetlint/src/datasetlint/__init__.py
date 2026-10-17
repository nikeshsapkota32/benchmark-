"""Offline checks for exact duplicate text and reused example IDs."""

import re


TEXT_POLICIES = ("exact", "ascii-whitespace-v1")
_ASCII_WHITESPACE = re.compile(r"[ \t\r\n\v\f]+")


def inspect(dataset, *, id_field="id", text_field="text", text_policy="exact"):
    _validate_fields(id_field, text_field)
    _validate_text_policy(text_policy)
    if not isinstance(dataset, dict) or type(dataset.get("schema_version")) is not int or dataset["schema_version"] != 1:
        raise ValueError("schema_version must be integer 1")
    splits = dataset.get("splits")
    _validate_splits(splits)
    for split, rows in splits.items():
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"split {split!r} must contain a nonempty list")
    return _inspect(splits, id_field=id_field, text_field=text_field, text_policy=text_policy)


def _validate_text_policy(text_policy):
    if text_policy not in TEXT_POLICIES:
        raise ValueError("text_policy must be exact or ascii-whitespace-v1")


def _validate_fields(id_field, text_field):
    if any(not isinstance(field, str) or not field.strip() for field in (id_field, text_field)):
        raise ValueError("id_field and text_field must be nonempty strings")
    if id_field == text_field:
        raise ValueError("id_field and text_field must be distinct")


def _validate_splits(splits):
    if not isinstance(splits, dict) or not splits:
        raise ValueError("splits must be a nonempty object")
    if any(not isinstance(name, str) or not name.strip() for name in splits):
        raise ValueError("split names must be nonempty strings")


def _inspect(splits, sources=None, *, id_field="id", text_field="text", text_policy="exact"):
    """Scan each iterable once; sources map JSONL indices to physical lines."""
    seen_ids, seen_texts, findings, counts = {}, {}, [], {}
    for split in sorted(splits):
        rows = splits[split]
        counts[split] = 0
        for index, row in enumerate(rows):
            where = f"{sources[split]}:{index + 1}" if sources else f"{split}[{index}]"
            if not isinstance(row, dict):
                raise ValueError(f"{where} must be an object")
            for role, field, seen in (("id", id_field, seen_ids), ("text", text_field, seen_texts)):
                value = row.get(field)
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f"{where}.{field} must be a nonempty string")
                if role == "text" and text_policy == "ascii-whitespace-v1":
                    value = _ASCII_WHITESPACE.sub(" ", value.strip(" \t\r\n\v\f"))
                if value in seen:
                    previous_split, previous_index = seen[value]
                    findings.append({"code": f"duplicate_{role}" if split == previous_split else f"overlap_{role}",
                                     "split": split, "index": index,
                                     "first_split": previous_split, "first_index": previous_index})
                    if sources:
                        findings[-1].update(path=sources[split], line=index + 1,
                                            first_path=sources[previous_split],
                                            first_line=previous_index + 1)
                else:
                    seen[value] = (split, index)
            counts[split] += 1
        if counts[split] == 0:
            where = sources[split] if sources else repr(split)
            raise ValueError(f"{where}: split must contain at least one record")
    report = {"schema_version": 1, "passed": not findings, "counts": counts, "findings": findings}
    if (id_field, text_field) != ("id", "text"):
        report["fields"] = {"id": id_field, "text": text_field}
    if text_policy != "exact":
        report["text_policy"] = text_policy
    return report
