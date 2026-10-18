"""Measure a synchronous callable on the current host."""

import inspect
import platform
import time

from .configuration import snapshot
from .compatibility import check_compatibility
from .report import summarize, validate_report


def _validate_sync_callable(callback, name):
    for target in (callback, getattr(callback, "__call__", None)):
        if inspect.iscoroutinefunction(target) or inspect.isasyncgenfunction(target):
            raise ValueError(f"{name} must be synchronous; async callbacks are unsupported")


def _call_sync(callback, name):
    result = callback()
    if inspect.isawaitable(result) or inspect.isasyncgen(result):
        # A wrapper can hide an async function from preflight inspection. Close
        # native coroutines to avoid an unawaited-coroutine warning, but do not
        # drive an event loop, await arbitrary objects or cancel caller tasks.
        if inspect.iscoroutine(result):
            result.close()
        raise ValueError(f"{name} returned an awaitable or async generator; synchronous completion is required")


def benchmark(operation, *, workload, warmups=3, repeats=10, synchronize=None,
              configuration=None):
    """Warm up, then time each completed call. Exceptions abort the run."""
    if not callable(operation) or (synchronize is not None and not callable(synchronize)):
        raise ValueError("operation and optional synchronize must be callable")
    _validate_sync_callable(operation, "operation")
    if synchronize is not None:
        _validate_sync_callable(synchronize, "synchronize")
    if not isinstance(workload, str) or not workload.strip():
        raise ValueError("workload must be a nonempty description")
    if type(warmups) is not int or warmups < 0 or type(repeats) is not int or repeats < 1:
        raise ValueError("warmups must be a nonnegative integer and repeats a positive integer")
    recorded_configuration = snapshot(configuration)
    complete = synchronize if synchronize is not None else lambda: None
    _call_sync(complete, "synchronize")
    for _ in range(warmups):
        _call_sync(operation, "operation")
        _call_sync(complete, "synchronize")
    durations = []
    for _ in range(repeats):
        start = time.perf_counter_ns()
        _call_sync(operation, "operation")
        _call_sync(complete, "synchronize")
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
