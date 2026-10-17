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


def fixture(kind="digits"):
    rows = [{"id": "synthetic/a", "target": "007", "prediction": "007"},
            {"id": "synthetic/b", "target": "3", "prediction": None}]
    if kind == "arithmetic":
        rows = [{"id": "synthetic/a", "operands": [3, 4], "operator": "+",
                 "target": 7, "prediction": 7},
                {"id": "synthetic/b", "operands": [0, 2], "operator": "*",
                 "target": 0, "prediction": None}]
    return {"schema_version": 1, "model": "synthetic-model", "dataset_revision": "fixture-v1",
            "protocol": "synthetic protocol", "kind": kind, "records": rows}


class BenchGuardExportTests(unittest.TestCase):
    def test_digits_metrics_directions_and_missing_sample_identity(self):
        report = to_benchguard(fixture())
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["model"], "synthetic-model")
        self.assertEqual(report["dataset_revision"], "fixture-v1")
        self.assertEqual(report["results"], [
            {"task": "visioneval/digits", "metric": metric, "value": value,
             "samples": 2, "higher_is_better": direction,
             "sample_ids": ["synthetic/a", "synthetic/b"]}
            for metric, value, direction in (("exact_match", 0.5, True),
                                              ("character_error_rate", 0.25, False))])
        self.assertNotIn("007", json.dumps(report))

    def test_arithmetic_exports_only_exact_match_and_keeps_zero(self):
        data = fixture("arithmetic")
        data["records"][1]["prediction"] = 0
        report = to_benchguard(data)
        self.assertEqual(len(report["results"]), 1)
        self.assertEqual(report["results"][0]["task"], "visioneval/arithmetic")
        self.assertEqual(report["results"][0]["value"], 1)
        self.assertTrue(report["results"][0]["higher_is_better"])

    def test_protocol_pins_export_version_kind_and_response_policy(self):
        data = fixture()
        data["protocol"] = 'prompt="नमस्ते"\nseed=42'
        strict = to_benchguard(data)
        parsed = json.loads(strict["protocol"])
        self.assertEqual(parsed, {"export": "visioneval-benchguard-v1", "kind": "digits",
                                  "protocol": data["protocol"], "response_policy": "strict"})
        numeric = to_benchguard(data, response_policy="numeric-text-v1")
        self.assertNotEqual(strict["protocol"], numeric["protocol"])
        data["protocol"] += ";new-prompt"
        self.assertNotEqual(strict["protocol"], to_benchguard(data)["protocol"])
        self.assertNotEqual(to_benchguard(fixture())["protocol"],
                            to_benchguard(fixture("arithmetic"))["protocol"])
        data = fixture()
        data["model"] = "candidate-model"
        self.assertEqual(to_benchguard(fixture())["protocol"], to_benchguard(data)["protocol"])

    def test_exports_are_deterministic_and_do_not_alias_input_or_other_metrics(self):
        data = fixture()
        original = deepcopy(data)
        result = to_benchguard(data)
        self.assertEqual(result, to_benchguard(dict(reversed(list(data.items())))))
        self.assertEqual(data, original)
        result["results"][0]["sample_ids"].append("extra")
        self.assertEqual(data, original)
        self.assertEqual(result["results"][1]["sample_ids"], ["synthetic/a", "synthetic/b"])
        data["records"].reverse()
        reordered = to_benchguard(data)
        self.assertEqual(reordered["results"][0]["sample_ids"], ["synthetic/b", "synthetic/a"])
        self.assertEqual(reordered["results"][0]["value"], result["results"][0]["value"])

    def test_invalid_records_and_policies_cannot_be_exported(self):
        invalid = []
        data = fixture()
        data["records"][1]["id"] = "synthetic/a"
        invalid.append(data)
        data = fixture("arithmetic")
        data["records"][1]["target"] = 9
        invalid.append(data)
        data = fixture()
        data["records"][1]["prediction"] = "ambiguous answer"
        invalid.append(data)
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(ValueError):
                to_benchguard(data)
        with self.assertRaises(ValueError):
            to_benchguard(fixture(), response_policy="guess")

    def test_error_rate_above_one_is_not_clipped(self):
        data = fixture()
        data["records"] = [{"id": "synthetic/a", "target": "1", "prediction": "1111"}]
        self.assertEqual(to_benchguard(data)["results"][1]["value"], 3)

    def test_cli_default_export_numeric_policy_and_details_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "predictions.json"
            data = fixture()
            path.write_text(json.dumps(data), encoding="utf-8")
            for flags, expected in (([], evaluate(data)), (["--format", "json"], evaluate(data)),
                                    (["--format", "benchguard"], to_benchguard(data)),
                                    (["--format", "benchguard", "--response-policy", "numeric-text-v1"],
                                     to_benchguard(data, response_policy="numeric-text-v1"))):
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    self.assertEqual(main([str(path), *flags]), 0)
                self.assertEqual(json.loads(out.getvalue()), expected)
                self.assertEqual(err.getvalue(), "")
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err), self.assertRaises(SystemExit) as error:
                main([str(path), "--format", "benchguard", "--details"])
            self.assertEqual(error.exception.code, 2)
            self.assertEqual(out.getvalue(), "")

    def test_cli_late_invalid_record_and_duplicate_keys_emit_no_partial_export(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "predictions.json"
            data = fixture()
            data["records"][1]["prediction"] = "bad answer"
            for raw in (json.dumps(data), '{"schema_version":1,"schema_version":1}'):
                path.write_text(raw, encoding="utf-8")
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    self.assertEqual(main([str(path), "--format", "benchguard"]), 2)
                self.assertEqual(out.getvalue(), "")
                self.assertTrue(err.getvalue())
