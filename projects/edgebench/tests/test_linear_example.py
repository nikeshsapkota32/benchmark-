"""Synthetic inference fixture tests, not model-quality measurements."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from edgebench import validate_report


EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "linear_classifier.py"
spec = importlib.util.spec_from_file_location("linear_example", EXAMPLE)
example = importlib.util.module_from_spec(spec)
spec.loader.exec_module(example)


class LinearExampleTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.model = self.root / "model.json"
        self.input = self.root / "input.json"
        self.model.write_text(json.dumps({"schema_version": 1,
            "weights": [[1, 2], [-1, 0]], "bias": [0, 3]}), encoding="utf-8")
        self.input.write_text(json.dumps({"schema_version": 1, "values": [2, 1]}), encoding="utf-8")

    def test_prediction_hashes_and_detached_loaded_state(self):
        operation, configuration = example.load_workload(self.model, self.input)
        self.assertEqual(operation(), 0)  # logits [4, 1]
        self.assertEqual(configuration["model_revision"], "sha256:" + hashlib.sha256(self.model.read_bytes()).hexdigest())
        self.assertEqual(configuration["input_revision"], "sha256:" + hashlib.sha256(self.input.read_bytes()).hexdigest())
        self.assertEqual(configuration["input_shape"], [2])
        self.assertEqual(configuration["batch_size"], 1)
        self.assertEqual(configuration["device"], "cpu")
        self.model.write_text("not JSON", encoding="utf-8")
        self.input.unlink()
        self.assertEqual(operation(), 0)  # no file reads during inference
        self.assertNotIn(str(self.root), json.dumps(configuration))

    def test_bias_and_first_index_tie_breaking(self):
        for bias, expected in (([0, 10], 1), ([0, 3], 0)):
            self.model.write_text(json.dumps({"schema_version": 1,
                "weights": [[1, 1], [0, 0]], "bias": bias}), encoding="utf-8")
            operation, _ = example.load_workload(self.model, self.input)
            self.assertEqual(operation(), expected)

        # Sequential accumulation loses the middle 1; compensated sum would not.
        self.model.write_text(json.dumps({"schema_version": 1,
            "weights": [[1e16, 1, -1e16], [0, 0, 0]], "bias": [0, 0.5]}), encoding="utf-8")
        self.input.write_text(json.dumps({"schema_version": 1, "values": [1, 1, 1]}), encoding="utf-8")
        operation, _ = example.load_workload(self.model, self.input)
        self.assertEqual(operation(), 1)

    def test_invalid_dimensions_and_numbers_are_rejected_before_benchmark(self):
        invalid = [
            {"weights": [], "bias": []}, {"weights": [[]], "bias": [0]},
            {"weights": [[1], [1, 2]], "bias": [0, 0]},
            {"weights": [[1, 2]], "bias": []}, {"weights": [[True, 2]], "bias": [0]},
            {"weights": [[1, "2"]], "bias": [0]}, {"weights": [[1, 2]], "bias": [None]},
            {"weights": [[10 ** 400, 2]], "bias": [0]},
            {"weights": [[1, 2]], "bias": [0], "unexpected": "ignored?"},
        ]
        for fields in invalid:
            with self.subTest(fields=fields):
                self.model.write_text(json.dumps({"schema_version": 1, **fields}), encoding="utf-8")
                with patch.object(example, "benchmark") as benchmark:
                    with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()):
                        self.assertEqual(example.main(["--model", str(self.model), "--input", str(self.input)]), 2)
                    benchmark.assert_not_called()
                    self.assertEqual(out.getvalue(), "")

    def test_invalid_input_and_json_syntax_fail_without_report(self):
        invalid = ['{"schema_version":1,"values":[1]}',
                   '{"schema_version":true,"values":[2,1]}',
                   '{"schema_version":1,"values":[2,false]}',
                   '{"schema_version":1,"values":[2,NaN]}',
                   '{"schema_version":1,"values":[2,1],"values":[3,1]}',
                   '[' * 10000 + '0' + ']' * 10000, '{', '[]']
        for payload in invalid:
            self.input.write_text(payload, encoding="utf-8")
            with self.subTest(payload=payload[:80]):
                with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
                    self.assertEqual(example.main(["--model", str(self.model), "--input", str(self.input)]), 2)
                self.assertEqual(out.getvalue(), "")
                self.assertNotIn("Traceback", err.getvalue())

    def test_loading_and_hashing_precede_all_timing_calls(self):
        events = []
        read_bytes = Path.read_bytes
        def read(path):
            events.append("read")
            return read_bytes(path)
        def tick():
            events.append("clock")
            return len(events) * 1_000_000
        with patch.object(Path, "read_bytes", read), patch("edgebench.time.perf_counter_ns", side_effect=tick):
            with redirect_stdout(io.StringIO()) as out:
                result = example.main(["--model", str(self.model), "--input", str(self.input),
                                       "--warmups", "1", "--repeats", "2"])
        self.assertEqual(result, 0)
        self.assertEqual(events, ["read", "read", "clock", "clock", "clock", "clock"])
        report = json.loads(out.getvalue())
        validate_report(report)
        self.assertEqual(report["durations"], [1, 1])
        self.assertEqual((report["warmups"], report["repeats"]), (1, 2))

    def test_nonfinite_forward_result_aborts_without_output(self):
        self.model.write_text(json.dumps({"schema_version": 1,
            "weights": [[1e308, 0]], "bias": [0]}), encoding="utf-8")
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            self.assertEqual(example.main(["--model", str(self.model), "--input", str(self.input),
                                           "--warmups", "0", "--repeats", "1"]), 2)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("nonfinite logit", err.getvalue())

    def test_bundled_synthetic_example_runs_and_validates(self):
        directory = EXAMPLE.parent
        operation, _ = example.load_workload(directory / "synthetic-linear-model.json",
                                              directory / "synthetic-linear-input.json")
        self.assertEqual(operation(), 1)  # hand-computed logits: [0, 3.5, -1.25]
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            result = example.main(["--model", str(directory / "synthetic-linear-model.json"),
                                   "--input", str(directory / "synthetic-linear-input.json"),
                                   "--warmups", "0", "--repeats", "2"])
        self.assertEqual((result, err.getvalue()), (0, ""))
        report = json.loads(out.getvalue())
        validate_report(report)
        self.assertEqual(report["configuration"]["input_shape"], [4])
        self.assertNotIn("accuracy", report)
        self.assertEqual(len(report["durations"]), 2)
