from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest

from visioneval import evaluate
from visioneval.__main__ import main
from visioneval.export import to_benchguard


def fixture():
    rows = [
        ("addition-correct", "+", [2, 3], 5, 5),
        ("addition-missing", "+", [0, 0], 0, None),
        ("subtraction-wrong", "-", [2, 5], -3, 3),
        ("multiplication-correct", "*", [0, 7], 0, 0),
        ("multiplication-missing", "*", [3, 4], 12, None),
    ]
    return {"schema_version": 1, "kind": "arithmetic", "model": "synthetic",
            "dataset_revision": "fixture-v1", "protocol": "synthetic arithmetic",
            "records": [{"id": item_id, "operator": op, "operands": operands,
                         "target": target, "prediction": prediction}
                        for item_id, op, operands, target, prediction in rows]}


class OperatorBreakdownTests(unittest.TestCase):
    def test_breakdown_reconciles_with_aggregate_and_details(self):
        data = fixture()
        original = deepcopy(data)
        report = evaluate(data, by_operator=True, include_details=True)
        self.assertEqual(data, original)
        self.assertEqual(list(report["operator_breakdown"]), ["+", "-", "*"])
        self.assertEqual(report["operator_breakdown"], {
            "+": {"samples": 2, "correct": 1, "missing": 1, "exact_match": 0.5},
            "-": {"samples": 1, "correct": 0, "missing": 0, "exact_match": 0.0},
            "*": {"samples": 2, "correct": 1, "missing": 1, "exact_match": 0.5},
        })
        self.assertEqual((report["samples"], report["correct"], report["missing"], report["exact_match"]),
                         (5, 2, 2, 0.4))
        for key in ("samples", "correct", "missing"):
            self.assertEqual(sum(item[key] for item in report["operator_breakdown"].values()), report[key])
        self.assertEqual([item["status"] for item in report["details"]],
                         ["correct", "missing", "incorrect", "correct", "missing"])
        for value in ("addition-correct", "subtraction-wrong"):
            self.assertNotIn(value, json.dumps(report))

    def test_absent_groups_omitted_and_all_missing_remain_in_denominator(self):
        data = fixture()
        data["records"] = [dict(row, prediction=None) for row in data["records"] if row["operator"] == "-"]
        report = evaluate(data, by_operator=True)
        self.assertEqual(report["operator_breakdown"], {
            "-": {"samples": 1, "correct": 0, "missing": 1, "exact_match": 0.0}})
        self.assertEqual(report["exact_match"], 0)

    def test_default_reports_and_benchguard_exports_remain_unchanged(self):
        data = fixture()
        baseline = evaluate(data)
        self.assertEqual(baseline, evaluate(data, by_operator=False))
        self.assertNotIn("operator_breakdown", baseline)
        report = evaluate(data, by_operator=True)
        report.pop("operator_breakdown")
        self.assertEqual(report, baseline)
        self.assertEqual(len(to_benchguard(data)["results"]), 1)
        digits = {**data, "kind": "digits", "records": [{"id": "a", "target": "1", "prediction": "1"}]}
        self.assertEqual(evaluate(digits), evaluate(digits, by_operator=False))

    def test_invalid_option_and_digit_inputs_are_rejected(self):
        for value in (None, 0, 1, "yes", [], {}):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "by_operator.*boolean"):
                evaluate(fixture(), by_operator=value)
        data = fixture()
        data["kind"] = "digits"
        with self.assertRaisesRegex(ValueError, "requires arithmetic"):
            evaluate(data, by_operator=True)

    def test_numeric_text_uses_parsed_answers_and_rejects_ambiguous_responses(self):
        data = fixture()
        for row in data["records"]:
            row["prediction"] = None if row["prediction"] is None else f" +{row['prediction']:04d} " if row["prediction"] >= 0 else f" {row['prediction']} "
        report = evaluate(data, by_operator=True, response_policy="numeric-text-v1")
        self.assertEqual(report["operator_breakdown"]["+"]["exact_match"], 0.5)
        self.assertEqual(report["operator_breakdown"]["*"]["correct"], 1)
        self.assertEqual(report["response_policy"], "numeric-text-v1")
        data["records"][-1]["prediction"] = "Maybe 12"
        with self.assertRaisesRegex(ValueError, "record 4"):
            evaluate(data, by_operator=True, response_policy="numeric-text-v1")

    def test_cli_opt_in_default_and_format_constraints(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "arithmetic.json"
            data = fixture()
            path.write_text(json.dumps(data), encoding="utf-8")
            for flags, expected in (([], evaluate(data)),
                                    (["--by-operator"], evaluate(data, by_operator=True)),
                                    (["--by-operator", "--details"],
                                     evaluate(data, by_operator=True, include_details=True))):
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    self.assertEqual(main([str(path), *flags]), 0)
                self.assertEqual(json.loads(out.getvalue()), expected)
                self.assertEqual(err.getvalue(), "")
            for flags in (("--format", "benchguard", "--by-operator"),
                          ("--by-operator", "--format", "benchguard")):
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err), self.assertRaises(SystemExit) as error:
                    main([str(path), *flags])
                self.assertEqual(error.exception.code, 2)
                self.assertEqual(out.getvalue(), "")

    def test_late_invalid_record_returns_no_partial_breakdown(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "arithmetic.json"
            data = fixture()
            data["records"].append({"id": "invalid", "operands": [1, 1], "operator": "+",
                                    "target": 9, "prediction": 9})
            path.write_text(json.dumps(data), encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(main([str(path), "--by-operator"]), 2)
            self.assertEqual(out.getvalue(), "")
            self.assertIn("target disagrees", err.getvalue())
