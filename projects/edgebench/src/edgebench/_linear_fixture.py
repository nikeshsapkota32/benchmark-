"""Shared, standard-library-only validation for the two linear examples."""

import hashlib
import json
import math

from .report import reject_constant, unique_object


def _load(path, fields):
    payload = path.read_bytes()
    try:
        data = json.loads(payload.decode("utf-8"), object_pairs_hook=unique_object,
                          parse_constant=reject_constant)
    except RecursionError:
        raise ValueError("JSON nesting exceeds parser limit") from None
    if not isinstance(data, dict) or set(data) != fields | {"schema_version"}:
        raise ValueError("unexpected or missing fixture fields")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("schema_version must be integer 1")
    return data, "sha256:" + hashlib.sha256(payload).hexdigest()


def _vector(values):
    if not isinstance(values, list) or not values:
        raise ValueError("vectors must be nonempty lists of finite numbers")
    converted = []
    for value in values:
        if type(value) not in (int, float):
            raise ValueError("vector entries must be finite numbers, not booleans")
        try:
            value = float(value)
        except OverflowError:
            raise ValueError("vector entry exceeds finite float range") from None
        if not math.isfinite(value):
            raise ValueError("vector entries must be finite numbers")
        converted.append(value)
    return tuple(converted)


def load_fixture(model_path, input_path):
    """Return detached numeric tuples and exact-byte identities; read each file once."""
    model, model_hash = _load(model_path, {"weights", "bias"})
    inputs, input_hash = _load(input_path, {"values"})
    if not isinstance(model["weights"], list) or not model["weights"]:
        raise ValueError("weights must be a nonempty list of row vectors")
    weights = tuple(_vector(row) for row in model["weights"])
    bias, values = _vector(model["bias"]), _vector(inputs["values"])
    if len(bias) != len(weights) or any(len(row) != len(values) for row in weights):
        raise ValueError("model and input dimensions do not match")
    return weights, bias, values, {
        "model": "dense-linear-argmax", "model_revision": model_hash,
        "input_revision": input_hash, "input_shape": [len(values)], "batch_size": 1,
    }
