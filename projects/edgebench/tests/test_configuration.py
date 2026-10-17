from contextlib import redirect_stdout
import io
import json
import unittest
from unittest.mock import Mock

from edgebench import benchmark
from edgebench.__main__ import main


class ConfigurationTests(unittest.TestCase):
    def test_complete_configuration_round_trips_in_report(self):
        configuration = {"model": "example", "model_revision": "weights-abc",
                         "runtime": "example-runtime", "runtime_version": "1.0",
                         "device": "cpu", "dtype": "float32", "input_shape": [1, 3, 28, 28],
                         "input_revision": "fixture-v1", "batch_size": 1, "threads": 2,
                         "protocol": "inference only; preprocessing excluded"}
        report = benchmark(lambda: None, workload="synthetic test", configuration=configuration,
                           warmups=0, repeats=1)
        self.assertEqual(json.loads(json.dumps(report))["configuration"], configuration)
        self.assertNotIn("model", report["environment"])

    def test_snapshot_precedes_execution_and_is_detached(self):
        configuration = {"runtime": "before", "input_shape": [1, 2]}
        def operation():
            configuration["runtime"] = "after"
            configuration["input_shape"][0] = 99
        report = benchmark(operation, workload="test", configuration=configuration,
                           warmups=1, repeats=1)
        self.assertEqual(report["configuration"], {"runtime": "before", "input_shape": [1, 2]})
        report["configuration"]["input_shape"][1] = 77
        self.assertEqual(configuration["input_shape"], [99, 2])

    def test_invalid_configuration_fails_before_any_work(self):
        cases = [[], "cpu", {"runtim": "typo"}, {1: "value"}]
        cases.extend({field: value} for field in ("model", "runtime", "protocol")
                     for value in ("", " ", None, 1, True))
        cases.extend({field: value} for field in ("threads", "batch_size")
                     for value in (0, -1, True, 1.5, "2"))
        cases.extend({"input_shape": value} for value in ([], [0], [-1], [True], [1.5], (1, 2), None))
        operation, synchronize = Mock(), Mock()
        for configuration in cases:
            with self.subTest(configuration=configuration), self.assertRaises(ValueError):
                benchmark(operation, workload="test", synchronize=synchronize,
                          configuration=configuration)
        operation.assert_not_called()
        synchronize.assert_not_called()

    def test_omitted_and_partial_configuration_remain_supported(self):
        for configuration, expected in ((None, {}), ({}, {}), ({"threads": 1}, {"threads": 1})):
            with self.subTest(configuration=configuration):
                report = benchmark(lambda: None, workload="test", configuration=configuration,
                                   warmups=0, repeats=1)
                self.assertEqual(report["configuration"], expected)

    def test_demo_records_its_actual_workload_configuration(self):
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["--demo", "--warmups", "0", "--repeats", "1"]), 0)
        report = json.loads(out.getvalue())
        self.assertEqual(report["configuration"]["runtime"], "Python/hashlib")
        self.assertEqual(report["configuration"]["runtime_version"], report["environment"]["python"])
        self.assertEqual(report["configuration"]["input_shape"], [1048576])
        self.assertEqual(report["configuration"]["dtype"], "bytes")
        self.assertNotIn("model", report["configuration"])
        self.assertIn("synthetic", report["workload"])
