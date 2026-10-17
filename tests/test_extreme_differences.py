"""Finite inputs can still produce a difference outside the float range."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

from benchguard.cli import main
from benchguard.core import compare
from test_samples import run


class ExtremeDifferenceTests(unittest.TestCase):
    def test_opposite_extremes_respect_score_direction(self):
        for before, after in ((10**308, -(10**308)), (1e308, -1e308),
                              (10**308, -1e308), (1e308, -(10**308))):
            for higher in (True, False):
                for improving in (True, False):
                    with self.subTest(before=before, after=after, higher=higher, improving=improving):
                        baseline = run(value=before)
                        candidate = run(value=after)
                        if improving == higher:
                            baseline, candidate = candidate, baseline
                        for item in (baseline, candidate):
                            item["results"][0]["higher_is_better"] = higher
                        row = compare(baseline, candidate, tolerance=1e308)[0]
                        self.assertEqual(row.status, "pass" if improving else "regression")

    def test_overflowing_difference_can_be_close_to_tolerance(self):
        maximum = sys.float_info.max
        for integer in (False, True):
            convert = int if integer else float
            with self.subTest(integer=integer):
                baseline, candidate = run(value=convert(maximum)), run(value=convert(-1e292))
                self.assertEqual(compare(baseline, candidate, maximum)[0].status, "pass")
                self.assertEqual(compare(baseline, candidate, maximum / 2)[0].status, "regression")

    def test_metric_override_uses_same_overflow_safe_comparison(self):
        baseline, candidate = run(value=sys.float_info.max), run(value=-1e292)
        row = compare(baseline, candidate,
                      metric_tolerances={"accuracy": sys.float_info.max})[0]
        self.assertEqual(row.status, "pass")

    def test_small_differences_keep_existing_absolute_tolerance(self):
        self.assertEqual(compare(run(value=0.0), run(value=-1e-16))[0].status, "pass")
        self.assertEqual(compare(run(value=0.0), run(value=-1e-14))[0].status, "regression")

    def test_cli_returns_regression_report_not_traceback(self):
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / "a.json", Path(directory) / "b.json"
            for magnitude in (10**308, 1e308):
                with self.subTest(magnitude=magnitude):
                    a.write_text(json.dumps(run(value=magnitude)), encoding="utf-8")
                    b.write_text(json.dumps(run(value=-magnitude)), encoding="utf-8")
                    output, errors = io.StringIO(), io.StringIO()
                    with redirect_stdout(output), redirect_stderr(errors):
                        code = main([str(a), str(b)])
                    self.assertEqual(code, 1)
                    self.assertEqual(errors.getvalue(), "")
                    report = json.loads(output.getvalue())
                    self.assertFalse(report["passed"])
                    self.assertEqual(report["results"][0]["status"], "regression")
                    self.assertTrue(math.isfinite(report["results"][0]["baseline"]))
                    self.assertTrue(math.isfinite(report["results"][0]["candidate"]))


if __name__ == "__main__":
    unittest.main()
