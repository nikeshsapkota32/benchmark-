"""Offline checks for exact duplicate text and reused example IDs."""

import re

from .indexes import open_indexes, validate_backend


TEXT_POLICIES = ("exact", "ascii-whitespace-v1")
_ASCII_WHITESPACE = re.compile(r"[ \t\r\n\v\f]+")


def inspect(dataset, *, id_field="id", text_field="text", text_policy="exact", max_findings=None,
            index_backend="memory", include_summary=False):
    _validate_fields(id_field, text_field)
    _validate_text_policy(text_policy)
    _validate_max_findings(max_findings)
    _validate_include_summary(include_summary)
    validate_backend(index_backend)
    if not isinstance(dataset, dict) or type(dataset.get("schema_version")) is not int or dataset["schema_version"] != 1:
        raise ValueError("schema_version must be integer 1")
    splits = dataset.get("splits")
    _validate_splits(splits)
    for split, rows in splits.items():
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"split {split!r} must contain a nonempty list")
    return _inspect(splits, id_field=id_field, text_field=text_field,
                    text_policy=text_policy, max_findings=max_findings, index_backend=index_backend,
                    include_summary=include_summary)


def _validate_include_summary(include_summary):
    if type(include_summary) is not bool:
        raise ValueError("include_summary must be a boolean")


def _validate_max_findings(max_findings):
    if max_findings is not None and (type(max_findings) is not int or max_findings < 0):
        raise ValueError("max_findings must be a nonnegative integer or None")


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


def _inspect(splits, sources=None, *, id_field="id", text_field="text", text_policy="exact",
             max_findings=None, index_backend="memory", include_summary=False):
    with open_indexes(index_backend) as (seen_ids, seen_texts):
        return _scan(splits, sources, id_field=id_field, text_field=text_field,
                     text_policy=text_policy, max_findings=max_findings,
                     seen_ids=seen_ids, seen_texts=seen_texts, include_summary=include_summary)


def _scan(splits, sources, *, id_field, text_field, text_policy, max_findings, seen_ids, seen_texts,
          include_summary=False):
    """Scan each iterable once; sources map JSONL indices to physical lines."""
    findings, counts = [], {}
    total_findings = 0
    finding_counts = {"duplicate_id": 0, "duplicate_text": 0, "overlap_id": 0, "overlap_text": 0}
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
                previous = seen.get(value)
                if previous is not None:
                    total_findings += 1
                    previous_split, previous_index = previous
                    code = f"duplicate_{role}" if split == previous_split else f"overlap_{role}"
                    if include_summary:
                        finding_counts[code] += 1
                    if max_findings is not None and len(findings) >= max_findings:
                        continue
                    findings.append({"code": code,
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
    report = {"schema_version": 1, "passed": total_findings == 0, "counts": counts, "findings": findings}
    if include_summary:
        report["finding_counts"] = finding_counts
    if max_findings is not None:
        report.update(max_findings=max_findings, total_findings=total_findings,
                      findings_truncated=total_findings > len(findings))
    if (id_field, text_field) != ("id", "text"):
        report["fields"] = {"id": id_field, "text": text_field}
    if text_policy != "exact":
        report["text_policy"] = text_policy
    return report
