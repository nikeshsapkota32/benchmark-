from contextlib import redirect_stderr, redirect_stdout
import io
import json
import unittest
from unittest.mock import Mock, patch

from edgebench import benchmark
from edgebench.__main__ import main


class TimingTests(unittest.TestCase):
    def test_warmups_and_percentiles(self):
        operation = Mock()
        clock = [0, 1_000_000, 2_000_000, 5_000_000, 6_000_000, 8_000_000]
        with patch("edgebench.time.perf_counter_ns", side_effect=clock) as timer:
            report = benchmark(operation, workload="test", warmups=2, repeats=3)
        self.assertEqual(operation.call_count, 5)
        self.assertEqual(timer.call_count, 6)
        self.assertEqual(report["durations"], [1, 3, 2])
        self.assertEqual(report["summary"], {"min": 1, "max": 3, "mean": 2, "median": 2, "p90": 3, "p95": 3})

    def test_synchronization_is_inside_timed_region(self):
        events = []
        def tick():
            events.append("clock")
            return len(events) * 1_000_000
        with patch("edgebench.time.perf_counter_ns", side_effect=tick):
            report = benchmark(lambda: events.append("op"), workload="test", warmups=0, repeats=1,
                               synchronize=lambda: events.append("sync"))
        self.assertEqual(events, ["sync", "clock", "op", "sync", "clock"])
        self.assertEqual(report["durations"], [3])

    def test_invalid_configuration_does_not_execute(self):
        operation = Mock()
        for options in ({"warmups": -1}, {"warmups": True}, {"repeats": 0}, {"repeats": 1.5},
                        {"synchronize": 1}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                benchmark(operation, workload="test", **options)
        operation.assert_not_called()

    def test_operation_errors_propagate(self):
        with self.assertRaisesRegex(RuntimeError, "failed"):
            benchmark(Mock(side_effect=RuntimeError("failed")), workload="test")

    def test_cli_and_host_metadata(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(main(["--demo", "--warmups", "0", "--repeats", "2"]), 0)
        report = json.loads(out.getvalue())
        self.assertEqual(len(report["durations"]), 2)
        self.assertTrue(report["environment"]["machine"])
        self.assertIn("not model inference", report["workload"])
        self.assertEqual(err.getvalue(), "")
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(main(["--demo", "--repeats", "0"]), 2)
