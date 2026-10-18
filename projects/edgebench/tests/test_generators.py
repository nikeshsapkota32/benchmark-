from functools import partial
import inspect
import unittest
from unittest.mock import Mock, patch

from edgebench import benchmark


class GeneratorTests(unittest.TestCase):
    def test_generator_callbacks_are_rejected_before_any_work(self):
        events = []

        def generate(value=None):
            events.append(value)
            yield value

        class GeneratorCallable:
            def __call__(self):
                yield from generate("object")

        for callback in (generate, partial(generate, "partial"),
                         GeneratorCallable(), GeneratorCallable().__call__):
            for role in ("operation", "synchronize"):
                other = Mock()
                with self.subTest(role=role, callback=callback):
                    with patch("edgebench.time.perf_counter_ns") as timer:
                        with self.assertRaisesRegex(ValueError, role + ".*generator"):
                            benchmark(callback if role == "operation" else other,
                                      synchronize=callback if role == "synchronize" else other,
                                      workload="synthetic generator", warmups=0, repeats=2)
                        timer.assert_not_called()
                    other.assert_not_called()
        self.assertEqual(events, [])

    def test_wrappers_fail_during_warmup_and_measurement_without_consuming(self):
        for warmups in (0, 1):
            events = []

            def generate():
                events.append("executed")
                yield 1

            generator = generate()
            self.addCleanup(generator.close)
            operation = Mock(return_value=generator)
            synchronize = Mock()
            with self.assertRaisesRegex(ValueError, "operation returned a generator"):
                benchmark(operation, workload="synthetic", warmups=warmups,
                          repeats=2, synchronize=synchronize)
            operation.assert_called_once_with()
            synchronize.assert_called_once_with()
            self.assertEqual(events, [])
            self.assertEqual(inspect.getgeneratorstate(generator), inspect.GEN_CREATED)

    def test_wrapped_synchronizer_checked_at_initial_warmup_and_measurement(self):
        for failure_call, warmups, operation_count in ((1, 0, 0), (2, 1, 1), (3, 1, 2)):
            generator = (x for x in range(1))
            self.addCleanup(generator.close)
            synchronize = Mock(side_effect=[None] * (failure_call - 1) + [generator])
            operation = Mock()
            with self.subTest(failure_call=failure_call):
                with self.assertRaisesRegex(ValueError, "synchronize returned a generator"):
                    benchmark(operation, synchronize=synchronize, workload="synthetic",
                              warmups=warmups, repeats=3)
                self.assertEqual(operation.call_count, operation_count)
                self.assertEqual(synchronize.call_count, failure_call)
                self.assertEqual(inspect.getgeneratorstate(generator), inspect.GEN_CREATED)

    def test_late_generator_aborts_without_closing_caller_owned_result(self):
        events = []

        def generate():
            try:
                yield 1
                events.append("resumed")
            finally:
                events.append("closed")

        generator = generate()
        self.addCleanup(generator.close)
        next(generator)
        operation = Mock(side_effect=[None, None, generator])
        with self.assertRaisesRegex(ValueError, "operation returned a generator"):
            benchmark(operation, workload="synthetic", warmups=1, repeats=3)
        self.assertEqual(operation.call_count, 3)
        self.assertEqual(events, [])
        self.assertEqual(inspect.getgeneratorstate(generator), inspect.GEN_SUSPENDED)

    def test_explicit_consumption_inside_callback_measures_completed_work(self):
        events = []

        def generate():
            events.append("generated")
            yield 1

        with patch("edgebench.time.perf_counter_ns", side_effect=[0, 1_000_000, 2_000_000, 4_000_000]):
            report = benchmark(lambda: list(generate()), workload="synthetic consumption",
                               warmups=1, repeats=2)
        self.assertEqual(events, ["generated"] * 3)
        self.assertEqual(report["durations"], [1, 2])
