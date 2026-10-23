from functools import partial
import inspect
import unittest
from unittest.mock import Mock, patch
import warnings

from edgebench import benchmark


class SyncContractTests(unittest.TestCase):
    def test_async_functions_methods_partials_and_callable_objects_fail_before_work(self):
        events = []

        async def operation(value=None):
            events.append(value)

        class AsyncCallable:
            async def __call__(self):
                events.append("call")

        callbacks = (operation, partial(operation, "partial"), AsyncCallable(), AsyncCallable().__call__)
        for callback in callbacks:
            with self.subTest(callback=callback):
                synchronize = Mock()
                with patch("edgebench.time.perf_counter_ns") as timer, self.assertRaisesRegex(ValueError, "operation.*synchronous"):
                    benchmark(callback, workload="synthetic", synchronize=synchronize)
                synchronize.assert_not_called()
                timer.assert_not_called()
        self.assertEqual(events, [])

    def test_async_synchronizers_are_rejected_before_the_operation(self):
        async def synchronize():
            raise AssertionError("must not execute")

        class AsyncSynchronizer:
            async def __call__(self):
                raise AssertionError("must not execute")

        for callback in (synchronize, partial(synchronize), AsyncSynchronizer()):
            operation = Mock()
            with self.assertRaisesRegex(ValueError, "synchronize.*synchronous"):
                benchmark(operation, workload="synthetic", synchronize=callback)
            operation.assert_not_called()

    def test_wrapped_coroutines_abort_warmup_and_measurement_without_warnings(self):
        for warmups in (0, 1):
            created, executed = [], []

            async def async_operation():
                executed.append(True)

            def wrapped():
                result = async_operation()
                created.append(result)
                return result

            synchronize = Mock()
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                with self.assertRaisesRegex(ValueError, "operation returned an awaitable"):
                    benchmark(wrapped, workload="synthetic", warmups=warmups, repeats=2,
                              synchronize=synchronize)
            self.assertEqual(len(created), 1)
            self.assertEqual(inspect.getcoroutinestate(created[0]), inspect.CORO_CLOSED)
            self.assertEqual(executed, [])
            self.assertEqual(caught, [])
            synchronize.assert_called_once_with()  # Only the initial synchronization.

    def test_wrapped_async_synchronization_is_checked_at_every_phase(self):
        for failure_call, warmups, expected_operations in ((1, 0, 0), (2, 1, 1), (3, 1, 2)):
            created = []

            async def async_sync():
                raise AssertionError("must not execute")

            calls = 0

            def synchronize():
                nonlocal calls
                calls += 1
                if calls == failure_call:
                    result = async_sync()
                    created.append(result)
                    return result

            operation = Mock()
            with self.subTest(failure_call=failure_call), self.assertRaisesRegex(ValueError, "synchronize returned"):
                benchmark(operation, workload="synthetic", warmups=warmups, repeats=3,
                          synchronize=synchronize)
            self.assertEqual(operation.call_count, expected_operations)
            self.assertEqual(calls, failure_call)
            self.assertEqual(inspect.getcoroutinestate(created[0]), inspect.CORO_CLOSED)

    def test_late_awaitable_does_not_produce_a_partial_report(self):
        events = []

        class Awaitable:
            def __await__(self):
                events.append("awaited")
                yield

            def cancel(self):
                events.append("cancelled")

        operation = Mock(side_effect=[None, None, Awaitable(), None])
        with self.assertRaisesRegex(ValueError, "operation returned an awaitable"):
            benchmark(operation, workload="synthetic", warmups=1, repeats=3)
        self.assertEqual(operation.call_count, 3)
        self.assertEqual(events, [])

    def test_async_generators_are_rejected_directly_and_through_wrappers(self):
        async def generate():
            yield 1

        class AsyncGeneratorCallable:
            async def __call__(self):
                yield 1

        for callback in (generate, partial(generate), AsyncGeneratorCallable(), lambda: generate()):
            for role in ("operation", "synchronize"):
                with self.subTest(role=role, callback=callback), self.assertRaisesRegex(ValueError, role):
                    benchmark(callback if role == "operation" else lambda: None,
                              synchronize=callback if role == "synchronize" else None,
                              workload="synthetic", warmups=0, repeats=1)

    def test_synchronous_outputs_and_callback_order_are_preserved(self):
        events = []
        outputs = iter((None, 0, {"prediction": 1}, [1, 2]))

        def operation():
            events.append("operation")
            return next(outputs)

        def synchronize():
            events.append("synchronize")
            return True

        with patch("edgebench.time.perf_counter_ns", side_effect=[0, 1_000_000, 2_000_000, 4_000_000]):
            report = benchmark(operation, workload="synthetic", warmups=2, repeats=2,
                               synchronize=synchronize)
        self.assertEqual(events, ["synchronize"] + ["operation", "synchronize"] * 4)
        self.assertEqual(report["durations"], [1, 2])

    def test_synchronous_callback_exceptions_still_propagate(self):
        for role in ("operation", "synchronize"):
            error = RuntimeError("synthetic failure")
            callback = Mock(side_effect=error)
            with self.assertRaises(RuntimeError) as caught:
                benchmark(callback if role == "operation" else lambda: None,
                          synchronize=callback if role == "synchronize" else None,
                          workload="synthetic")
            self.assertIs(caught.exception, error)
