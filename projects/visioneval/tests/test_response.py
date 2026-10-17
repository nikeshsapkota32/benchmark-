from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest

from visioneval import evaluate
from visioneval.__main__ import main


def fixture(kind="digits"):
    return {"schema_version": 1, "model": "synthetic", "dataset_revision": "fixture-v1",
            "protocol": "synthetic numeric responses", "kind": kind,
            "records": [{"id": "private-id", "target": "007", "prediction": " \t007\r\n"}]}


class ResponsePolicyTests(unittest.TestCase):
    def test_digits_preserve_leading_zeros_and_input(self):
        data = fixture()
        original = deepcopy(data)
        report = evaluate(data, response_policy="numeric-text-v1", include_details=True)
        self.assertEqual(data, original)
        self.assertEqual(report["correct"], 1)
        self.assertEqual(report["digit_edit_errors"], 0)
        self.assertEqual(report["target_digits"], 3)
        self.assertEqual(report["response_policy"], "numeric-text-v1")
        self.assertEqual(report["details"][0]["status"], "correct")
        self.assertNotIn("private-id", json.dumps(report))
        self.assertNotIn("007", json.dumps(report))
        data["records"][0]["prediction"] = "7"
        report = evaluate(data, response_policy="numeric-text-v1")
        self.assertEqual(report["correct"], 0)
        self.assertEqual(report["digit_edit_errors"], 2)

    def test_signed_integer_responses_and_zero(self):
        for response, target in ((" +003\n", 3), (" -12 ", -12), ("-0", 0), ("0", 0)):
            with self.subTest(response=response):
                data = fixture("arithmetic")
                data["records"] = [{"id": "a", "operands": [target, 0], "operator": "+",
                                    "target": target, "prediction": response}]
                report = evaluate(data, response_policy="numeric-text-v1", include_details=True)
                self.assertEqual(report["correct"], 1)
                self.assertEqual(report["missing"], 0)
                self.assertEqual(report["details"], [{"index": 0, "status": "correct"}])

    def test_blank_and_null_remain_in_denominator(self):
        for kind in ("digits", "arithmetic"):
            data = fixture(kind)
            data["records"] = [{"id": str(index), "target": "007" if kind == "digits" else 7,
                                "prediction": prediction, "operands": [3, 4], "operator": "+"}
                               for index, prediction in enumerate((None, "", " \t\n\v\f\r"))]
            report = evaluate(data, response_policy="numeric-text-v1", include_details=True)
            self.assertEqual((report["samples"], report["missing"], report["exact_match"]), (3, 3, 0))
            self.assertTrue(all(item["status"] == "missing" for item in report["details"]))
            if kind == "digits":
                self.assertEqual(report["digit_edit_errors"], 9)

    def test_ambiguous_prose_expressions_and_unicode_are_rejected(self):
        invalid = ("Answer: 7", "7 or 8", "3+4", "7.0", "1e3", "1_000", "1,000",
                   "```7```", "٧", "７", "\u00a07\u00a0", "7 8", "+", "--7", "−7")
        for kind in ("digits", "arithmetic"):
            for response in invalid:
                with self.subTest(kind=kind, response=response):
                    data = fixture(kind)
                    data["records"][0]["prediction"] = response
                    with self.assertRaisesRegex(ValueError, "record 0: numeric-text-v1") as error:
                        evaluate(data, response_policy="numeric-text-v1")
                    self.assertNotIn("private-id", str(error.exception))
                    self.assertNotIn(response, str(error.exception))
        for response in ("+007", "-007"):
            data = fixture()
            data["records"][0]["prediction"] = response
            with self.assertRaises(ValueError):
                evaluate(data, response_policy="numeric-text-v1")

    def test_types_options_and_arithmetic_length_limit(self):
        for prediction in (7, True, 7.0, [], {}):
            data = fixture()
            data["records"][0]["prediction"] = prediction
            with self.assertRaisesRegex(ValueError, "string or null"):
                evaluate(data, response_policy="numeric-text-v1")
        for policy in (None, True, [], {}, "numeric", ""):
            with self.assertRaises(ValueError):
                evaluate(fixture(), response_policy=policy)
        data = fixture("arithmetic")
        data["records"] = [{"id": "a", "target": 0, "operands": [0, 0], "operator": "+",
                            "prediction": "0" * 1000}]
        self.assertEqual(evaluate(data, response_policy="numeric-text-v1")["correct"], 1)
        data["records"][0]["prediction"] += "0"
        with self.assertRaisesRegex(ValueError, "exceeds 1000 digits"):
            evaluate(data, response_policy="numeric-text-v1")

    def test_strict_defaults_and_targets_are_unchanged(self):
        data = fixture()
        with self.assertRaises(ValueError):
            evaluate(data)
        data["records"][0]["prediction"] = "007"
        baseline = evaluate(data)
        self.assertEqual(baseline, evaluate(data, response_policy="strict"))
        self.assertNotIn("response_policy", baseline)
        data["records"][0]["target"] = " 007 "
        with self.assertRaisesRegex(ValueError, "digit targets"):
            evaluate(data, response_policy="numeric-text-v1")
        data = fixture("arithmetic")
        data["records"] = [{"id": "a", "target": 8, "prediction": "8",
                            "operands": [3, 4], "operator": "+"}]
        with self.assertRaisesRegex(ValueError, "target disagrees"):
            evaluate(data, response_policy="numeric-text-v1")

    def test_cli_policy_details_and_late_error_no_partial_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "responses.json"
            data = fixture()
            path.write_text(json.dumps(data), encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(main([str(path), "--response-policy", "numeric-text-v1", "--details"]), 0)
            report = json.loads(out.getvalue())
            self.assertEqual(report["response_policy"], "numeric-text-v1")
            self.assertEqual(report["details"][0]["status"], "correct")
            self.assertEqual(err.getvalue(), "")
            data["records"].append({"id": "b", "target": "7", "prediction": "private answer: 7 or 8"})
            path.write_text(json.dumps(data), encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(main([str(path), "--response-policy", "numeric-text-v1"]), 2)
            self.assertEqual(out.getvalue(), "")
            self.assertIn("record 1", err.getvalue())
            self.assertNotIn("private answer", err.getvalue())
