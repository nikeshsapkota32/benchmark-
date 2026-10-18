from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from edgebench import compare_reports
from edgebench.__main__ import main
from edgebench.report import summarize
from test_compatibility import fixture


def timing(values):
    report = fixture()
    report.update(durations=values, repeats=len(values), summary=summarize(values))
    return report


class ComparisonTests(unittest.TestCase):
    def test_all_summary_deltas_have_explicit_units_and_order(self):
        before, after = timing([1, 2, 3, 4]), timing([2, 4, 6, 8])
        original = deepcopy((before, after))
        result = compare_reports(before, after)
        self.assertEqual(result["report_type"], "edgebench-comparison")
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["unit"], "ms")
        self.assertTrue(result["compatibility"]["compatible"])
        self.assertEqual(result["metrics"], [
            {"metric": key, "baseline": value, "candidate": value * 2, "delta_ms": value}
            for key, value in (("min", 1), ("max", 4), ("mean", 2.5),
                               ("median", 2.5), ("p90", 4), ("p95", 4))])
        self.assertEqual((before, after), original)
        self.assertEqual(result, compare_reports(before, after))

    def test_faster_unchanged_zero_and_extreme_finite_timings(self):
        for left, right in ((2, 1), (1, 1), (0, 0), (0, 1),
                            (0, sys.float_info.max), (sys.float_info.max, 0),
                            (0, 5e-324)):
            with self.subTest(left=left, right=right):
                result = compare_reports(timing([left]), timing([right]))
                self.assertTrue(result["compatibility"]["compatible"])
                self.assertTrue(all(row["delta_ms"] == right - left for row in result["metrics"]))
                json.dumps(result, allow_nan=False)

    def test_rounding_in_saved_summary_does_not_create_a_false_delta(self):
        before, after = timing([1, 2]), timing([1, 2])
        after["summary"]["mean"] += 1e-13
        after["summary"]["median"] -= 1e-13
        self.assertTrue(all(row["delta_ms"] == 0 for row in compare_reports(before, after)["metrics"]))

    def test_incompatible_reports_have_diagnostics_but_no_numeric_comparison(self):
        before, after = timing([1]), timing([2])
        after["configuration"]["protocol"] = "changed"
        result = compare_reports(before, after)
        self.assertEqual(result["metrics"], [])
        self.assertEqual(result["compatibility"]["differences"], [
            {"field": "configuration.protocol", "reason": "different"}])
        self.assertEqual(compare_reports(timing([1]), timing([1, 2]))["metrics"], [])

    def test_required_and_controlled_fields_reuse_compatibility_rules(self):
        before, after = timing([1]), timing([2])
        after["configuration"]["threads"] = 4
        self.assertEqual(compare_reports(before, after)["metrics"], [])
        result = compare_reports(before, after, vary_fields=["threads"], required_fields=["input_shape"])
        self.assertEqual(len(result["metrics"]), 6)
        self.assertEqual(result["compatibility"]["policy"], "controlled-fields-v1")
        self.assertEqual(len(result["compatibility"]["permitted_differences"]), 1)
        self.assertEqual(compare_reports(before, after, vary_fields=["threads"],
                                         required_fields=["model_revision"])["metrics"], [])

    def test_invalid_reports_and_policies_raise_instead_of_returning_partial_data(self):
        invalid = timing([1])
        invalid["summary"]["mean"] = 99
        for before, after in ((invalid, fixture()), (fixture(), invalid)):
            with self.assertRaises(ValueError):
                compare_reports(before, after)
        for options in ({"required_fields": ["unknown"]}, {"vary_fields": ["protocol"]}):
            with self.assertRaises(ValueError):
                compare_reports(fixture(), fixture(), **options)

    def test_no_raw_timings_or_metadata_values_are_copied(self):
        report = timing([1, 2, 3])
        report["workload"] = "private-workload"
        report["configuration"]["protocol"] = "private-protocol"
        result = compare_reports(report, report)
        encoded = json.dumps(result)
        self.assertNotIn("private-", encoded)
        self.assertNotIn("durations", encoded)
        self.assertNotIn("passed", result)

    def test_cli_exit_codes_no_workload_and_no_partial_invalid_output(self):
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / "a.json", Path(directory) / "b.json"
            a.write_text(json.dumps(timing([1])), encoding="utf-8")
            for case, expected in (("slower", 0), ("controlled", 0), ("incompatible", 1),
                                   ("invalid", 2), ("duplicate", 2), ("bad_utf8", 2)):
                after = timing([2])
                if case == "controlled":
                    after["configuration"]["threads"] = 4
                if case == "incompatible":
                    after["configuration"]["protocol"] = "changed"
                if case == "invalid":
                    after["summary"]["mean"] = 99
                b.write_text(json.dumps(after), encoding="utf-8")
                if case == "duplicate":
                    b.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
                if case == "bad_utf8":
                    b.write_bytes(b"\xff")
                out, err = io.StringIO(), io.StringIO()
                with patch("edgebench.__main__.benchmark") as runner, redirect_stdout(out), redirect_stderr(err):
                    code = main(["--compare", str(a), str(b), "--vary-field", "threads",
                                 "--require-field", "input_shape"])
                runner.assert_not_called()
                self.assertEqual(code, expected, case)
                if expected == 2:
                    self.assertEqual(out.getvalue(), "")
                    self.assertTrue(err.getvalue())
                else:
                    self.assertEqual(err.getvalue(), "")
                    result = json.loads(out.getvalue())
                    self.assertEqual(len(result["metrics"]), 6 if expected == 0 else 0)

    def test_cli_modes_remain_mutually_exclusive(self):
        for args in (["--compare", "a", "b", "--demo"],
                     ["--compare", "a", "b", "--check-compatible", "a", "b"],
                     ["--compare", "a", "b", "--repeats", "1"]):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                main(args)
            self.assertEqual(error.exception.code, 2)
