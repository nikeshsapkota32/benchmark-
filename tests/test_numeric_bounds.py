"""Out-of-range JSON integers should produce input errors, not tracebacks."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from benchguard.cli import main
from benchguard.core import compare, failed


def result(value):
    return {
        "schema_version": 1,
        "model": "synthetic",
        "dataset_revision": "fixture-v1",
        "protocol": "test-only",
        "results": [{"task": "demo", "metric": "score", "value": value,
                     "samples": 1, "higher_is_better": True}],
    }


class NumericBoundsTests(unittest.TestCase):
    def test_out_of_range_scores_are_value_errors(self):
        for value in (10 ** 400, -(10 ** 400)):
            for baseline, candidate in ((result(value), result(1)),
                                        (result(1), result(value))):
                with self.subTest(sign=value > 0), self.assertRaises(ValueError):
                    compare(baseline, candidate)

    def test_out_of_range_api_tolerances_are_value_errors(self):
        for value in (10 ** 400, -(10 ** 400)):
            with self.subTest(sign=value > 0), self.assertRaises(ValueError):
                compare(result(1), result(1), value)

    def test_large_representable_integer_remains_supported(self):
        value = 10 ** 300
        self.assertFalse(failed(compare(result(value), result(value))))

    def test_cli_reports_input_error_without_partial_output(self):
        with tempfile.TemporaryDirectory() as directory:
            baseline, candidate = Path(directory) / "baseline.json", Path(directory) / "candidate.json"
            for value in (10 ** 400, -(10 ** 400)):
                for a, b in ((value, 1), (1, value)):
                    baseline.write_text(json.dumps(result(a)), encoding="utf-8")
                    candidate.write_text(json.dumps(result(b)), encoding="utf-8")
                    output, errors = io.StringIO(), io.StringIO()
                    with self.subTest(sign=value > 0, baseline_overflows=a == value):
                        with redirect_stdout(output), redirect_stderr(errors):
                            self.assertEqual(main([str(baseline), str(candidate)]), 2)
                        self.assertEqual(output.getvalue(), "")
                        self.assertIn("benchguard: value", errors.getvalue())
                        self.assertNotIn("Traceback", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
