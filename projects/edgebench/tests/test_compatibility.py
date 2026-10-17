from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from edgebench import check_compatibility
from edgebench.__main__ import main


def fixture():
    return {"schema_version": 1, "workload": "synthetic test", "warmups": 0, "repeats": 1,
            "environment": {"system": "test-os", "release": "1", "machine": "test-arch", "python": "3.12"},
            "configuration": {"protocol": "fixture-v1", "threads": 2, "input_shape": [1, 2]},
            "unit": "ms", "percentile_method": "nearest_rank", "durations": [1],
            "summary": {"min": 1, "max": 1, "mean": 1, "median": 1, "p90": 1, "p95": 1}}


class CompatibilityTests(unittest.TestCase):
    def test_matching_metadata_with_different_timings_and_no_mutation(self):
        baseline, candidate = fixture(), fixture()
        candidate["durations"] = [2]
        candidate["summary"] = dict.fromkeys(candidate["summary"], 2)
        original = deepcopy((baseline, candidate))
        result = check_compatibility(baseline, candidate, required_fields=["threads", "threads"])
        self.assertEqual(result, {"schema_version": 1, "policy": "strict-metadata-v1", "compatible": True,
                                  "required_fields": ["protocol", "threads"], "differences": []})
        self.assertEqual((baseline, candidate), original)

    def test_changed_workload_counts_environment_and_configuration(self):
        changes = [("workload", "other"), ("warmups", 1), ("repeats", 2),
                   ("environment.machine", "other"), ("environment.python", "3.13"),
                   ("configuration.protocol", "other"), ("configuration.threads", 3),
                   ("configuration.input_shape", [2, 1])]
        for field, value in changes:
            with self.subTest(field=field):
                candidate = fixture()
                if "." in field:
                    parent, key = field.split(".")
                    candidate[parent][key] = value
                else:
                    candidate[field] = value
                if field == "repeats":
                    candidate["durations"] = [1, 1]
                result = check_compatibility(fixture(), candidate)
                self.assertFalse(result["compatible"])
                self.assertEqual(result["differences"], [{"field": field, "reason": "different"}])

    def test_absent_configuration_and_required_fields_are_not_defaults(self):
        baseline, candidate = fixture(), fixture()
        del baseline["configuration"]
        del candidate["configuration"]
        result = check_compatibility(baseline, candidate, required_fields=["model_revision"])
        self.assertEqual(result["differences"], [
            {"field": "configuration.model_revision", "reason": "missing_in_both"},
            {"field": "configuration.protocol", "reason": "missing_in_both"}])
        candidate = fixture()
        del candidate["configuration"]["threads"]
        self.assertEqual(check_compatibility(fixture(), candidate)["differences"],
                         [{"field": "configuration.threads", "reason": "missing_in_candidate"}])
        self.assertEqual(check_compatibility(candidate, fixture())["differences"],
                         [{"field": "configuration.threads", "reason": "missing_in_baseline"}])

    def test_blank_environment_is_missing_and_values_are_not_echoed(self):
        baseline, candidate = fixture(), fixture()
        baseline["environment"]["machine"] = candidate["environment"]["machine"] = " "
        candidate["configuration"]["protocol"] = "private-protocol"
        result = check_compatibility(baseline, candidate)
        self.assertFalse(result["compatible"])
        self.assertIn({"field": "environment.machine", "reason": "missing_in_both"}, result["differences"])
        self.assertNotIn("private-protocol", json.dumps(result))

    def test_invalid_policies_and_malformed_reports_raise(self):
        for fields in (None, "threads", {}, ["unknown"], [1], [True]):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                check_compatibility(fixture(), fixture(), required_fields=fields)
        invalid = fixture()
        invalid["summary"]["mean"] = 99
        for baseline, candidate in ((invalid, fixture()), (fixture(), invalid)):
            with self.assertRaisesRegex(ValueError, "does not match"):
                check_compatibility(baseline, candidate)

    def test_cli_exit_codes_without_running_a_workload(self):
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / "a.json", Path(directory) / "b.json"
            a.write_text(json.dumps(fixture()), encoding="utf-8")
            candidate = fixture()
            for kind, code in (("matching", 0), ("different", 1), ("invalid", 2)):
                if kind == "different":
                    candidate["configuration"]["threads"] = 4
                if kind == "invalid":
                    candidate["durations"] = [-1]
                b.write_text(json.dumps(candidate), encoding="utf-8")
                out, err = io.StringIO(), io.StringIO()
                with patch("edgebench.__main__.benchmark") as runner, redirect_stdout(out), redirect_stderr(err):
                    self.assertEqual(main(["--check-compatible", str(a), str(b), "--require-field", "threads"]), code)
                runner.assert_not_called()
                if code == 2:
                    self.assertEqual(out.getvalue(), "")
                    self.assertTrue(err.getvalue())
                else:
                    self.assertEqual(json.loads(out.getvalue())["compatible"], code == 0)

    def test_cli_rejects_conflicting_modes_and_unrelated_flags(self):
        for args in (["--demo", "--check-compatible", "a", "b"],
                     ["--demo", "--require-field", "threads"],
                     ["--check-compatible", "a", "b", "--warmups", "1"]):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                main(args)
            self.assertEqual(error.exception.code, 2)
