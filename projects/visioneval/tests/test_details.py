from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

from visioneval import evaluate
from visioneval.__main__ import main
from test_scoring import data


class DetailTests(unittest.TestCase):
    def test_digit_details_reconcile_with_aggregates(self):
        item = data()
        item["records"] = [
            {"id": "correct", "target": "012", "prediction": "012"},
            {"id": "deletion", "target": "012", "prediction": "12"},
            {"id": "insertion", "target": "1", "prediction": "1111"},
            {"id": "null", "target": "23", "prediction": None},
            {"id": "empty", "target": "4", "prediction": ""},
        ]
        report = evaluate(item, include_details=True)
        details = report["details"]
        self.assertEqual([row["index"] for row in details], list(range(5)))
        self.assertEqual([row["status"] for row in details],
                         ["correct", "incorrect", "incorrect", "missing", "missing"])
        self.assertEqual([row["digit_edit_errors"] for row in details], [0, 1, 3, 2, 1])
        self.assertEqual(sum(row["digit_edit_errors"] for row in details), report["digit_edit_errors"])
        self.assertEqual(sum(row["target_digits"] for row in details), report["target_digits"])
        self.assertEqual(sum(row["status"] == "correct" for row in details), report["correct"])
        self.assertEqual(sum(row["status"] == "missing" for row in details), report["missing"])

    def test_arithmetic_zero_negative_and_missing_outcomes(self):
        item = data("arithmetic")
        item["records"] = [
            {"id": "zero", "operands": [3, 3], "operator": "-", "target": 0, "prediction": 0},
            {"id": "negative", "operands": [2, 5], "operator": "-", "target": -3, "prediction": 3},
            {"id": "absent", "operands": [2, 5], "operator": "*", "target": 10, "prediction": None},
        ]
        report = evaluate(item, include_details=True)
        self.assertEqual(report["details"], [{"index": 0, "status": "correct"},
                                            {"index": 1, "status": "incorrect"},
                                            {"index": 2, "status": "missing"}])
        self.assertEqual((report["correct"], report["missing"]), (1, 1))

    def test_raw_record_fields_are_not_copied(self):
        item = data()
        item["records"][0].update(id="private-identifier", target="987654321", prediction="987654320",
                                  image="private/path.png", notes="private-note")
        report = evaluate(item, include_details=True)
        self.assertEqual(set(report["details"][0]), {"index", "status", "digit_edit_errors", "target_digits"})
        encoded = json.dumps(report)
        for value in ("private-identifier", "987654321", "987654320", "private/path.png", "private-note"):
            self.assertNotIn(value, encoded)

    def test_default_aggregates_and_inputs_are_unchanged(self):
        item = data()
        original = copy.deepcopy(item)
        basic = evaluate(item)
        report = evaluate(item, include_details=True)
        details = report.pop("details")
        self.assertEqual(report, basic)
        self.assertNotIn("details", basic)
        details[0]["status"] = "modified"
        self.assertEqual(item, original)

    def test_invalid_option_is_rejected(self):
        for flag in (1, 0, "yes", None, []):
            with self.subTest(flag=flag), self.assertRaisesRegex(ValueError, "boolean"):
                evaluate(data(), include_details=flag)

    def test_cli_details_and_late_error_without_partial_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.json"
            item = data()
            path.write_text(json.dumps(item), encoding="utf-8")
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(main([str(path), "--details"]), 0)
            self.assertEqual(json.loads(out.getvalue())["details"][0]["status"], "correct")
            item["records"].append({"id": "bad", "target": "2", "prediction": True})
            path.write_text(json.dumps(item), encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(main([str(path), "--details"]), 2)
            self.assertEqual(out.getvalue(), "")
            self.assertTrue(err.getvalue())
