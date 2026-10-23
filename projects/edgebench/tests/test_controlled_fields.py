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
from test_compatibility import fixture


class ControlledFieldsTests(unittest.TestCase):
    def test_declared_variation_is_reported_without_mutating_inputs(self):
        before, after = fixture(), fixture()
        after["configuration"]["threads"] = 4
        original = deepcopy((before, after))
        self.assertFalse(check_compatibility(before, after)["compatible"])
        result = check_compatibility(before, after, vary_fields=["threads", "threads"],
                                     required_fields=["threads"])
        self.assertEqual(result, {"schema_version": 1, "policy": "controlled-fields-v1",
                                 "compatible": True, "required_fields": ["protocol", "threads"],
                                 "vary_fields": ["threads"], "differences": [],
                                 "permitted_differences": [{"field": "configuration.threads", "reason": "different"}]})
        self.assertEqual((before, after), original)

    def test_empty_variation_preserves_strict_report_and_unchanged_fields_are_not_differences(self):
        self.assertEqual(check_compatibility(fixture(), fixture(), vary_fields=[]),
                         check_compatibility(fixture(), fixture()))
        result = check_compatibility(fixture(), fixture(), vary_fields=("threads",))
        self.assertTrue(result["compatible"])
        self.assertEqual(result["permitted_differences"], [])

    def test_declared_fields_must_be_present_on_both_sides(self):
        for missing in ("baseline", "candidate", "both"):
            with self.subTest(missing=missing):
                before, after = fixture(), fixture()
                if missing in ("baseline", "both"):
                    del before["configuration"]["threads"]
                if missing in ("candidate", "both"):
                    del after["configuration"]["threads"]
                result = check_compatibility(before, after, vary_fields=["threads"])
                self.assertFalse(result["compatible"])
                self.assertEqual(result["differences"], [
                    {"field": "configuration.threads", "reason": "missing_in_" + missing}])
                self.assertEqual(result["permitted_differences"], [])

    def test_other_configuration_environment_protocol_and_counts_stay_strict(self):
        for field, value in (("configuration.input_shape", [2, 1]),
                             ("configuration.protocol", "other"),
                             ("environment.machine", "other"), ("environment.system", " "),
                             ("warmups", 1), ("repeats", 2), ("workload", "other")):
            with self.subTest(field=field):
                after = fixture()
                after["configuration"]["threads"] = 4
                if "." in field:
                    parent, key = field.split(".")
                    after[parent][key] = value
                else:
                    after[field] = value
                if field == "repeats":
                    after["durations"] = [1, 1]
                result = check_compatibility(fixture(), after, vary_fields=["threads"])
                self.assertFalse(result["compatible"])
                self.assertEqual([row["field"] for row in result["differences"]], [field])
                self.assertEqual(len(result["permitted_differences"]), 1)

    def test_multiple_variations_are_deterministic_and_do_not_echo_values(self):
        before, after = fixture(), fixture()
        before["configuration"]["dtype"] = "private-baseline-value"
        after["configuration"].update(dtype="private-candidate-value", threads=4)
        result = check_compatibility(before, after, vary_fields=["threads", "dtype"])
        self.assertEqual(result, check_compatibility(before, after, vary_fields=["dtype", "threads"]))
        self.assertEqual(result["vary_fields"], ["dtype", "threads"])
        self.assertEqual([row["field"] for row in result["permitted_differences"]],
                         ["configuration.dtype", "configuration.threads"])
        self.assertNotIn("private-", json.dumps(result))

    def test_invalid_policy_and_malformed_reports_cannot_bypass_validation(self):
        for fields in (None, "threads", {}, ["unknown"], [True], [1], ["protocol"],
                       ["environment.machine"], ["repeats"]):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                check_compatibility(fixture(), fixture(), vary_fields=fields)
        for where in ("baseline", "candidate"):
            before, after = fixture(), fixture()
            invalid = before if where == "baseline" else after
            invalid["configuration"]["threads"] = False
            with self.assertRaises(ValueError):
                check_compatibility(before, after, vary_fields=["threads"])
            invalid["configuration"]["threads"] = 4
            invalid["summary"]["mean"] = 99
            with self.assertRaises(ValueError):
                check_compatibility(before, after, vary_fields=["threads"])

    def test_cli_exit_codes_and_no_workload_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / "a.json", Path(directory) / "b.json"
            a.write_text(json.dumps(fixture()), encoding="utf-8")
            for case, expected in (("allowed", 0), ("missing", 1), ("invalid", 2)):
                after = fixture()
                after["configuration"]["threads"] = 4
                if case == "missing":
                    del after["configuration"]["threads"]
                if case == "invalid":
                    after["durations"] = [-1]
                b.write_text(json.dumps(after), encoding="utf-8")
                out, err = io.StringIO(), io.StringIO()
                with patch("edgebench.__main__.benchmark") as runner, redirect_stdout(out), redirect_stderr(err):
                    code = main(["--check-compatible", str(a), str(b), "--vary-field", "threads",
                                 "--require-field", "input_shape"])
                runner.assert_not_called()
                self.assertEqual(code, expected)
                if expected == 2:
                    self.assertEqual(out.getvalue(), "")
                    self.assertTrue(err.getvalue())
                else:
                    self.assertEqual(err.getvalue(), "")
                    self.assertEqual(json.loads(out.getvalue())["compatible"], expected == 0)

    def test_cli_variation_option_requires_compatibility_mode(self):
        for args in (["--demo"], ["--validate", "unused.json"]):
            with patch("edgebench.__main__.benchmark") as runner, redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                main(args + ["--vary-field", "threads"])
            runner.assert_not_called()
            self.assertEqual(error.exception.code, 2)
