"""Synthetic response-policy examples; no model inference or private data."""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from visioneval import evaluate
from visioneval.__main__ import main
from visioneval.export import to_benchguard


POLICY = "numeric-text-count-v1"


def fixture(kind="digits"):
    responses = [" 007\n", "8", None, " \t", "private response: 7"]
    return {"schema_version": 1, "model": "synthetic", "dataset_revision": "fixture-v1",
            "protocol": "synthetic-only", "kind": kind,
            "records": [{"id": f"private-id-{index}", "target": "007" if kind == "digits" else 7,
                         "prediction": value, "operands": [3, 4], "operator": "+"}
                        for index, value in enumerate(responses)]}


class ResponseAccountingTests(unittest.TestCase):
    def test_digits_keep_all_records_and_distinguish_unparseable_from_missing(self):
        data = fixture()
        original = deepcopy(data)
        report = evaluate(data, response_policy=POLICY, include_details=True)
        self.assertEqual(data, original)
        self.assertEqual((report["samples"], report["correct"], report["missing"],
                          report["unparseable"]), (5, 1, 2, 1))
        self.assertEqual(report["exact_match"], 0.2)
        self.assertEqual(report["unparseable_rate"], 0.2)
        self.assertEqual(report["response_policy"], POLICY)
        self.assertEqual([row["status"] for row in report["details"]],
                         ["correct", "incorrect", "missing", "missing", "unparseable"])
        self.assertEqual(report["digit_edit_errors"], 12)
        self.assertEqual(report["target_digits"], 15)
        self.assertEqual(report["character_error_rate"], 0.8)
        self.assertEqual(report["details"][-1]["digit_edit_errors"], 3)
        self.assertNotIn("private", json.dumps(report))
        self.assertNotIn("007", json.dumps(report))

    def test_arithmetic_operator_totals_and_empty_prediction_status(self):
        data = fixture("arithmetic")
        data["records"].append({"id": "minus", "target": 0, "operands": [1, 1],
                                "operator": "-", "prediction": "-0"})
        report = evaluate(data, response_policy=POLICY, by_operator=True, include_details=True)
        self.assertEqual((report["correct"], report["missing"], report["unparseable"]), (2, 2, 1))
        self.assertEqual(report["unparseable_rate"], 1 / 6)
        self.assertEqual(report["operator_breakdown"], {
            "+": {"samples": 5, "correct": 1, "missing": 2, "unparseable": 1,
                  "exact_match": 0.2, "unparseable_rate": 0.2},
            "-": {"samples": 1, "correct": 1, "missing": 0, "unparseable": 0,
                  "exact_match": 1.0, "unparseable_rate": 0.0}})
        self.assertEqual(report["details"][-1]["status"], "correct")

    def test_whole_response_grammar_and_conversion_limit(self):
        invalid = ["Answer: 7", "7 or 8", "3+4", "7.0", "1e3", "1,000", "```7```",
                   "٧", "７", "\u00a07", "+", "--7", "−7", "\u200b"]
        for kind in ("digits", "arithmetic"):
            for response in invalid + (["+007", "-007"] if kind == "digits" else ["0" * 1001]):
                with self.subTest(kind=kind, response=response):
                    data = fixture(kind)
                    data["records"] = [dict(data["records"][0], prediction=response)]
                    report = evaluate(data, response_policy=POLICY)
                    self.assertEqual((report["correct"], report["missing"], report["unparseable_rate"]),
                                     (0, 0, 1.0))
        data = fixture("arithmetic")
        data["records"] = [dict(data["records"][0], prediction="0" * 999 + "7")]
        self.assertEqual(evaluate(data, response_policy=POLICY)["correct"], 1)

    def test_nontext_types_and_invalid_labels_are_still_errors(self):
        for value in (7, True, 7.0, [], {}):
            data = fixture()
            data["records"][0]["prediction"] = value
            with self.assertRaisesRegex(ValueError, "string or null"):
                evaluate(data, response_policy=POLICY)
        for kind in ("digits", "arithmetic"):
            data = fixture(kind)
            data["records"][-1]["target"] = "invalid" if kind == "digits" else 8
            with self.assertRaises(ValueError):
                evaluate(data, response_policy=POLICY)

    def test_existing_policies_and_valid_response_scores_are_unchanged(self):
        for kind in ("digits", "arithmetic"):
            data = fixture(kind)
            with self.assertRaises(ValueError):
                evaluate(data, response_policy="numeric-text-v1")
            with self.assertRaises(ValueError):
                evaluate(data)
            data["records"].pop()
            old = evaluate(data, response_policy="numeric-text-v1", include_details=True)
            new = evaluate(data, response_policy=POLICY, include_details=True)
            self.assertEqual(new.pop("unparseable"), 0)
            self.assertEqual(new.pop("unparseable_rate"), 0.0)
            new["response_policy"] = "numeric-text-v1"
            self.assertEqual(new, old)

    def test_internal_parser_errors_are_not_counted_as_response_failures(self):
        with patch("visioneval.numeric_text", side_effect=ValueError("internal parser error")):
            with self.assertRaisesRegex(ValueError, "internal parser error"):
                evaluate(fixture(), response_policy=POLICY)

    def test_export_pins_policy_and_retains_ids_for_parse_failure_metric(self):
        for kind in ("digits", "arithmetic"):
            data = fixture(kind)
            exported = to_benchguard(data, response_policy=POLICY)
            protocol = json.loads(exported["protocol"])
            self.assertEqual(protocol["response_policy"], POLICY)
            metrics = {row["metric"]: row for row in exported["results"]}
            self.assertEqual(metrics["unparseable_rate"]["value"], 0.2)
            self.assertFalse(metrics["unparseable_rate"]["higher_is_better"])
            for row in metrics.values():
                self.assertEqual(row["samples"], 5)
                self.assertEqual(row["sample_ids"], [item["id"] for item in data["records"]])
            self.assertNotIn("private response", json.dumps(exported))

    def test_cli_scoring_and_late_schema_error_have_atomic_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.json"
            for output_format in ("json", "benchguard"):
                data = fixture()
                for valid in (True, False):
                    if not valid:
                        data["records"][-1]["prediction"] = False
                    path.write_text(json.dumps(data), encoding="utf-8")
                    out, err = io.StringIO(), io.StringIO()
                    with redirect_stdout(out), redirect_stderr(err):
                        result = main([str(path), "--response-policy", POLICY, "--format", output_format])
                    self.assertEqual(result, 0 if valid else 2)
                    if valid:
                        self.assertEqual(err.getvalue(), "")
                        self.assertIsInstance(json.loads(out.getvalue()), dict)
                    else:
                        self.assertEqual(out.getvalue(), "")
                        self.assertIn("record 4", err.getvalue())
                        self.assertNotIn("private", err.getvalue())
