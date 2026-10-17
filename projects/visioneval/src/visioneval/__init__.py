"""Score saved digit and arithmetic predictions without running a model."""

import operator


def edit_distance(a, b):
    previous = list(range(len(b) + 1))
    for i, left in enumerate(a, 1):
        current = [i]
        for j, right in enumerate(b, 1):
            current.append(min(current[-1] + 1, previous[j] + 1,
                               previous[j - 1] + (left != right)))
        previous = current
    return previous[-1]


def evaluate(data, *, include_details=False):
    if type(include_details) is not bool:
        raise ValueError("include_details must be a boolean")
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ValueError("schema_version must be integer 1")
    for name in ("model", "dataset_revision", "protocol"):
        if not isinstance(data.get(name), str) or not data[name].strip():
            raise ValueError(f"{name} must be a nonempty string")
    kind = data.get("kind")
    if kind not in ("digits", "arithmetic"):
        raise ValueError("kind must be digits or arithmetic")
    rows = data.get("records")
    if not isinstance(rows, list) or not rows:
        raise ValueError("records must be a nonempty list")
    seen, correct, missing, edits, digits = set(), 0, 0, 0, 0
    details = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"].strip():
            raise ValueError(f"record {index} needs a nonempty string id")
        if row["id"] in seen:
            raise ValueError("duplicate record id")
        seen.add(row["id"])
        if "prediction" not in row:
            raise ValueError(f"record {index} needs prediction (use null for missing)")
        target, prediction = row.get("target"), row["prediction"]
        if kind == "digits":
            if not isinstance(target, str) or not target or any(c not in "0123456789" for c in target):
                raise ValueError("digit targets must be nonempty ASCII digit strings")
            if prediction is not None and (not isinstance(prediction, str) or any(c not in "0123456789" for c in prediction)):
                raise ValueError("digit predictions must be ASCII digit strings or null")
            is_missing = prediction is None or prediction == ""
            record_edits = edit_distance(target, prediction or "")
            edits += record_edits
            digits += len(target)
        else:
            operands, op = row.get("operands"), row.get("operator")
            operations = {"+": operator.add, "-": operator.sub, "*": operator.mul}
            if not isinstance(operands, list) or len(operands) != 2 or any(type(x) is not int for x in operands):
                raise ValueError("arithmetic operands must be two integers")
            if not isinstance(op, str) or op not in operations:
                raise ValueError("operator must be +, - or *")
            if type(target) is not int or target != operations[op](*operands):
                raise ValueError("arithmetic target disagrees with operands/operator")
            if prediction is not None and type(prediction) is not int:
                raise ValueError("arithmetic prediction must be an integer or null")
            is_missing = prediction is None
        is_correct = prediction == target
        missing += is_missing
        correct += is_correct
        if include_details:
            detail = {"index": index,
                      "status": "missing" if is_missing else "correct" if is_correct else "incorrect"}
            if kind == "digits":
                detail.update(digit_edit_errors=record_edits, target_digits=len(target))
            details.append(detail)
    report = {"schema_version": 1, "kind": kind,
              **{key: data[key] for key in ("model", "dataset_revision", "protocol")},
              "samples": len(rows), "correct": correct, "missing": missing,
              "exact_match": correct / len(rows)}
    if kind == "digits":
        report.update({"digit_edit_errors": edits, "target_digits": digits,
                       "character_error_rate": edits / digits})
    if include_details:
        report["details"] = details
    return report
