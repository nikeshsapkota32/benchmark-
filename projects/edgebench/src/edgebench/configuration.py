"""Validate and snapshot caller-reported workload settings before execution."""

STRING_FIELDS = {"model", "model_revision", "runtime", "runtime_version", "device",
                 "dtype", "input_revision", "protocol"}
INTEGER_FIELDS = {"batch_size", "threads"}
CONFIGURATION_FIELDS = STRING_FIELDS | INTEGER_FIELDS | {"input_shape"}


def snapshot(configuration):
    if configuration is None:
        return {}
    if not isinstance(configuration, dict):
        raise ValueError("configuration must be an object")
    result = {}
    for name, value in configuration.items():
        if not isinstance(name, str) or name not in CONFIGURATION_FIELDS:
            raise ValueError(f"unknown configuration field: {name!r}")
        if name in STRING_FIELDS:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"configuration.{name} must be a nonempty string")
        elif name in INTEGER_FIELDS:
            if type(value) is not int or value < 1:
                raise ValueError(f"configuration.{name} must be a positive integer")
        else:
            if not isinstance(value, list) or not value or any(type(dim) is not int or dim < 1 for dim in value):
                raise ValueError("configuration.input_shape must be a nonempty list of positive integers")
            value = list(value)
        result[name] = value
    return result
