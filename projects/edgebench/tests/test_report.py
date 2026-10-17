from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from edgebench import benchmark, validate_report
from edgebench.__main__ import main
from edgebench.report import summarize


class ReportTests(unittest.TestCase):
    def setUp(self):
        # Synthetic timings from a controlled clock, not hardware results.
        with patch("edgebench.time.perf_counter_ns", side_effect=[0, 1_000_000, 0, 3_000_000]):
            self.report = benchmark(lambda: None, workload="synthetic fixture", warmups=0, repeats=2)

    def test_generated_roundtrip_and_legacy_reports_without_mutation(self):
        report = json.loads(json.dumps(self.report))
        original = deepcopy(report)
        self.assertIsNone(validate_report(report))
        self.assertEqual(report, original)
        del report["configuration"]
        report["environment"]["machine"] = ""  # platform may return unavailable metadata
        report["future_extension"] = "ignored"
        self.assertIsNone(validate_report(report))

    def test_schema_metadata_and_configuration_errors(self):
        cases = {"schema_version": [True, 1.0, 2, None], "workload": [None, "", " "],
                 "warmups": [-1, True, 0.0], "repeats": [0, True, 2.0],
                 "unit": ["s", None], "percentile_method": ["linear", None],
                 "environment": [None, {}, {"system": 3}],
                 "configuration": [None, [], {"threads": 0}, {"unknown": 1}]}
        for key, values in cases.items():
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    validate_report(dict(self.report, **{key: value}))
        for key in set(self.report) - {"configuration"}:
            with self.subTest(missing=key), self.assertRaises(ValueError):
                validate_report({k: v for k, v in self.report.items() if k != key})

    def test_duration_count_type_and_numeric_errors(self):
        for durations in (None, [], [1], [1, 2, 3], (1, 3)):
            with self.subTest(durations=durations), self.assertRaises(ValueError):
                validate_report(dict(self.report, durations=durations))
        for invalid in (True, "1", None, -1, float("nan"), float("inf"), 10 ** 400):
            with self.subTest(invalid=str(invalid)[:30]), self.assertRaises(ValueError):
                validate_report(dict(self.report, durations=[invalid, 3]))

    def test_every_summary_metric_is_checked(self):
        for key in self.report["summary"]:
            for invalid in (None, True, "1", -1, float("nan"), float("inf"), 10 ** 400, 99):
                with self.subTest(key=key, invalid=str(invalid)[:30]), self.assertRaises(ValueError):
                    report = deepcopy(self.report)
                    report["summary"][key] = invalid
                    validate_report(report)

    def test_known_percentiles_and_even_odd_medians(self):
        # Independent expected values, not derived from the summarizer under test.
        for durations, expected in (([3, 1, 2], {"min": 1, "max": 3, "mean": 2, "median": 2, "p90": 3, "p95": 3}),
                                    (list(range(1, 21)), {"min": 1, "max": 20, "mean": 10.5, "median": 10.5, "p90": 18, "p95": 19})):
            self.assertEqual(summarize(durations), expected)
            report = dict(self.report, durations=durations, repeats=len(durations), summary=expected)
            self.assertIsNone(validate_report(report))

    def test_zero_singleton_and_extreme_finite_timings(self):
        for durations in ([0], [0, 0], [1e308, 1e308]):
            expected = {name: durations[0] for name in ("min", "max", "mean", "median", "p90", "p95")}
            self.assertEqual(summarize(durations), expected)
            self.assertIsNone(validate_report(dict(self.report, durations=durations,
                                                   repeats=len(durations), summary=expected)))

    def test_only_mean_and_median_allow_small_rounding_error(self):
        for key in ("mean", "median"):
            report = deepcopy(self.report)
            report["summary"][key] *= 1 + 5e-13
            self.assertIsNone(validate_report(report))
            report["summary"][key] *= 1 + 1e-8
            with self.assertRaises(ValueError):
                validate_report(report)
        report = deepcopy(self.report)
        report["summary"]["p95"] += 1e-13
        with self.assertRaises(ValueError):
            validate_report(report)

    def test_cli_validates_without_execution_or_echoing_workload(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text(json.dumps(self.report), encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with patch("edgebench.__main__.benchmark") as runner, redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(main(["--validate", str(path)]), 0)
            runner.assert_not_called()
            self.assertEqual(json.loads(out.getvalue()), {"valid": True, "schema_version": 1, "repeats": 2})
            self.assertEqual(err.getvalue(), "")

    def test_cli_rejects_invalid_files_without_partial_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            cases = [b'bad', b'\xff', b'{"schema_version":1,"schema_version":1}',
                     b'{"extra":NaN}', b'[]', json.dumps(dict(self.report, repeats=99)).encode()]
            for payload in cases + [None]:
                if payload is None:
                    path.unlink()
                else:
                    path.write_bytes(payload)
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    self.assertEqual(main(["--validate", str(path)]), 2)
                self.assertEqual(out.getvalue(), "")
                self.assertTrue(err.getvalue())

    def test_cli_rejects_mixed_modes_and_timing_flags_on_validation(self):
        for args in (["--demo", "--validate", "report.json"],
                     ["--validate", "report.json", "--warmups", "0"],
                     ["--validate", "report.json", "--repeats", "2"]):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                main(args)
            self.assertEqual(error.exception.code, 2)
