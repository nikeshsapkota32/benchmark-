"""Measure a synchronous callable on the current host."""

import platform
import time

from .configuration import snapshot
from .report import summarize, validate_report


def benchmark(operation, *, workload, warmups=3, repeats=10, synchronize=None,
              configuration=None):
    """Warm up, then time each completed call. Exceptions abort the run."""
    if not callable(operation) or (synchronize is not None and not callable(synchronize)):
        raise ValueError("operation and optional synchronize must be callable")
    if not isinstance(workload, str) or not workload.strip():
        raise ValueError("workload must be a nonempty description")
    if type(warmups) is not int or warmups < 0 or type(repeats) is not int or repeats < 1:
        raise ValueError("warmups must be a nonnegative integer and repeats a positive integer")
    recorded_configuration = snapshot(configuration)
    complete = synchronize if synchronize is not None else lambda: None
    complete()
    for _ in range(warmups):
        operation()
        complete()
    durations = []
    for _ in range(repeats):
        start = time.perf_counter_ns()
        operation()
        complete()
        duration = time.perf_counter_ns() - start
        if duration < 0:
            raise ValueError("monotonic clock moved backwards")
        durations.append(duration / 1_000_000)
    return {"schema_version": 1, "workload": workload, "warmups": warmups, "repeats": repeats,
            "configuration": recorded_configuration,
            "environment": {"system": platform.system(), "release": platform.release(),
                            "machine": platform.machine(), "python": platform.python_version()},
            "unit": "ms", "percentile_method": "nearest_rank",
            "durations": durations,
            "summary": summarize(durations)}
