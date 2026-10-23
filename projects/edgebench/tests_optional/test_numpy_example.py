"""Optional CPU correctness/protocol tests, never performance assertions."""

import builtins
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import threadpoolctl

from edgebench import benchmark, check_compatibility, validate_report


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def load_example(name):
    spec = importlib.util.spec_from_file_location(name, EXAMPLES / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


example = load_example("numpy_linear_classifier")
stdlib_example = load_example("linear_classifier")


class NumPyExampleTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.model = self.root / "model.json"
        self.input = self.root / "input.json"
        self.write_model([[1, 2], [-1, 0]], [0, 3])
        self.input.write_text('{"schema_version":1,"values":[2,1]}', encoding="utf-8")

    def write_model(self, weights, bias):
        self.model.write_text(json.dumps({"schema_version": 1, "weights": weights,
                                         "bias": bias}), encoding="utf-8")

    def cli(self, *options):
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            code = example.main(["--model", str(self.model), "--input", str(self.input),
                                 "--warmups", "0", "--repeats", "2", *options])
        return code, out.getvalue(), err.getvalue()

    def test_prediction_hashes_and_immutable_preloaded_arrays(self):
        operation, configuration = example._load_workload(np, self.model, self.input)
        self.assertEqual(operation(), 0)  # hand-computed logits [4, 1]
        for field, path in (("model_revision", self.model), ("input_revision", self.input)):
            self.assertEqual(configuration[field], "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest())
        arrays = [cell.cell_contents for cell in operation.__closure__
                  if isinstance(cell.cell_contents, np.ndarray)]
        self.assertEqual(len(arrays), 3)
        for array in arrays:
            self.assertEqual(array.dtype, np.float64)
            self.assertTrue(array.flags.c_contiguous)
            self.assertFalse(array.flags.writeable)
            with self.assertRaises(ValueError):
                array.flat[0] = 99
        self.model.unlink()
        self.input.unlink()
        self.assertEqual(operation(), 0)

    def test_bias_and_first_index_ties(self):
        for bias, expected in (([0, 10], 1), ([0, 3], 0)):
            with self.subTest(bias=bias):
                self.write_model([[1, 1], [0, 0]], bias)
                operation, _ = example._load_workload(np, self.model, self.input)
                self.assertEqual(operation(), expected)

    def test_bundled_synthetic_example(self):
        operation, _ = example._load_workload(np, EXAMPLES / "synthetic-linear-model.json",
                                              EXAMPLES / "synthetic-linear-input.json")
        self.assertEqual(operation(), 1)  # hand-computed logits [0, 3.5, -1.25]

    def test_invalid_dimensions_and_numbers_precede_benchmark(self):
        for weights, bias in (([], []), ([[]], [0]), ([[1], [1, 2]], [0, 0]),
                              ([[1, 2]], []), ([[True, 2]], [0]), ([[1, "2"]], [0]),
                              ([[1, 2]], [None]), ([[10 ** 400, 2]], [0]),
                              ([[float("inf"), 2]], [0])):
            with self.subTest(weights=weights, bias=bias):
                self.write_model(weights, bias)
                with patch.object(example, "benchmark") as measure:
                    code, stdout, _ = self.cli()
                self.assertEqual((code, stdout), (2, ""))
                measure.assert_not_called()

    def test_invalid_json_schema_and_encoding_precede_benchmark(self):
        payloads = [b'{"schema_version":1,"values":[1]}',
                    b'{"schema_version":true,"values":[2,1]}',
                    b'{"schema_version":1,"values":[2,false]}',
                    b'{"schema_version":1,"values":[2,NaN]}',
                    b'{"schema_version":1,"values":[2,1],"values":[3,1]}',
                    b'{"schema_version":1,"values":[2,1],"extra":1}',
                    b'[' * 10000 + b'0' + b']' * 10000, b'{', b'[]', b'\xff']
        for payload in payloads:
            with self.subTest(payload=payload[:80]):
                self.input.write_bytes(payload)
                with patch.object(example, "benchmark") as measure:
                    code, stdout, stderr = self.cli()
                self.assertEqual((code, stdout), (2, ""))
                self.assertNotIn("Traceback", stderr)
                measure.assert_not_called()

    def test_report_round_trip_metadata_and_thread_restoration(self):
        before = threadpoolctl.threadpool_info()
        code, stdout, stderr = self.cli("--threads", "1")
        self.assertEqual((code, stderr), (0, ""))
        self.assertEqual(threadpoolctl.threadpool_info(), before)
        report = json.loads(stdout)
        validate_report(report)
        self.assertTrue(check_compatibility(report, deepcopy(report))["compatible"])
        configuration = report["configuration"]
        self.assertEqual(configuration["threads"], 1)
        self.assertEqual(configuration["input_shape"], [2])
        self.assertEqual(configuration["dtype"], "float64")
        versions = json.loads(configuration["runtime_version"])
        self.assertEqual(versions["numpy"], np.__version__)
        self.assertEqual(versions["threadpoolctl"], threadpoolctl.__version__)
        self.assertTrue(versions["blas"])
        for backend in versions["blas"]:
            self.assertEqual(set(backend), {"internal_api", "version", "threading_layer", "architecture"})
        for forbidden in (str(self.root), "filepath", "prediction", "weights"):
            self.assertNotIn(forbidden, json.dumps(configuration))

    def test_setup_and_thread_control_are_outside_timed_intervals(self):
        events = []
        read_bytes, array, info = Path.read_bytes, np.array, threadpoolctl.threadpool_info
        isfinite, argmax = np.isfinite, np.argmax

        def read(path):
            events.append("read")
            return read_bytes(path)

        def convert(*args, **kwargs):
            events.append("convert")
            return array(*args, **kwargs)

        def inspect_threads():
            events.append("threads")
            result = info()
            self.assertTrue(result)
            self.assertTrue(all(item["num_threads"] == 1 for item in result if item["user_api"] == "blas"))
            return result

        def finite(*args):
            events.append("finite")
            return isfinite(*args)

        def select(*args):
            events.append("argmax")
            self.assertTrue(all(item["num_threads"] == 1 for item in info() if item["user_api"] == "blas"))
            return argmax(*args)

        def tick():
            events.append("clock")
            return len(events) * 1_000_000

        with patch.object(Path, "read_bytes", read), patch.object(np, "array", convert), \
                patch.object(threadpoolctl, "threadpool_info", inspect_threads), \
                patch.object(np, "isfinite", finite), patch.object(np, "argmax", select), \
                patch("edgebench.time.perf_counter_ns", side_effect=tick):
            report = example.run(self.model, self.input, warmups=1, repeats=2)
        self.assertEqual(events, ["read", "read", "convert", "convert", "convert", "threads",
                                  "finite", "argmax", "clock", "finite", "argmax", "clock",
                                  "clock", "finite", "argmax", "clock", "threads"])
        self.assertEqual(report["durations"], [3, 3])
        validate_report(report)

    def test_nonfinite_result_aborts_and_restores_threads(self):
        self.write_model([[1e308, 0]], [0])
        before = threadpoolctl.threadpool_info()
        code, stdout, stderr = self.cli()
        self.assertEqual((code, stdout), (2, ""))
        self.assertIn("nonfinite logit", stderr)
        self.assertNotIn("RuntimeWarning", stderr)
        self.assertEqual(threadpoolctl.threadpool_info(), before)

    def test_arbitrary_measurement_failure_restores_threads(self):
        before = threadpoolctl.threadpool_info()
        with patch.object(example, "benchmark", side_effect=RuntimeError("synthetic failure")):
            with self.assertRaisesRegex(RuntimeError, "synthetic failure"):
                example.run(self.model, self.input)
        self.assertEqual(threadpoolctl.threadpool_info(), before)

    def test_missing_dependencies_give_actionable_error_without_report(self):
        original_import = builtins.__import__
        for missing in ("numpy", "threadpoolctl"):
            def import_module(name, *args, **kwargs):
                if name == missing:
                    raise ImportError("synthetic missing dependency")
                return original_import(name, *args, **kwargs)
            with self.subTest(missing=missing), patch("builtins.__import__", side_effect=import_module):
                code, stdout, stderr = self.cli()
            self.assertEqual((code, stdout), (2, ""))
            self.assertIn("numpy-example", stderr)

    def test_invalid_threads_precede_loading(self):
        for threads in (True, 0, -1, 1.5, "1"):
            with self.subTest(threads=threads), patch.object(example, "_dependencies") as dependencies:
                with self.assertRaisesRegex(ValueError, "threads must be"):
                    example.run(self.model, self.input, threads=threads)
                dependencies.assert_not_called()
        self.assertEqual(self.cli("--threads", "0")[:2], (2, ""))

    def test_unverifiable_backend_rejects_before_timing_and_restores(self):
        before = threadpoolctl.threadpool_info()
        invalid = [[], [{"user_api": "openmp", "num_threads": 1}],
                   [{"user_api": "blas", "num_threads": 2, "version": "x"}],
                   [{"user_api": "blas", "num_threads": True, "version": "x"}],
                   [{"user_api": "blas", "num_threads": 1, "version": None}]]
        for info in invalid:
            with self.subTest(info=info), patch.object(threadpoolctl, "threadpool_info", return_value=info), \
                    patch.object(example, "benchmark") as measure:
                self.assertEqual(self.cli()[:2], (2, ""))
                measure.assert_not_called()
            self.assertEqual(threadpoolctl.threadpool_info(), before)

    def test_backend_change_during_run_rejects_report(self):
        with threadpoolctl.threadpool_limits(limits=1, user_api="blas"):
            initial = threadpoolctl.threadpool_info()
        changed = deepcopy(initial)
        changed[0]["version"] += "-changed"
        with patch.object(threadpoolctl, "threadpool_info", side_effect=[initial, changed]):
            code, stdout, stderr = self.cli()
        self.assertEqual((code, stdout), (2, ""))
        self.assertIn("changed during measurement", stderr)

    def test_stdlib_and_numpy_protocols_cannot_be_compared(self):
        report = example.run(self.model, self.input, warmups=0, repeats=2)
        operation, configuration = stdlib_example.load_workload(self.model, self.input)
        baseline = benchmark(operation, workload=report["workload"], configuration=configuration,
                             warmups=0, repeats=2)
        result = check_compatibility(baseline, report,
                                    vary_fields=["runtime", "runtime_version", "dtype"])
        self.assertFalse(result["compatible"])
        self.assertIn({"field": "configuration.protocol", "reason": "different"}, result["differences"])

    def test_changed_threads_require_explicit_variation(self):
        report = example.run(self.model, self.input, warmups=0, repeats=1)
        candidate = deepcopy(report)
        candidate["configuration"]["threads"] = 2  # synthetic metadata comparison, not a measurement
        self.assertFalse(check_compatibility(report, candidate)["compatible"])
        self.assertTrue(check_compatibility(report, candidate, vary_fields=["threads"])["compatible"])


if __name__ == "__main__":
    unittest.main()
