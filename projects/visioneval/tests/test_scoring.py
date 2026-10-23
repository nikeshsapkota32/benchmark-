from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

from visioneval import evaluate
from visioneval.__main__ import main


def data(kind="digits"):
    row = {"id": "a", "target": "012", "prediction": "012"} if kind == "digits" else {
        "id": "a", "operands": [7, 3], "operator": "-", "target": 4, "prediction": 4}
    return {"schema_version": 1, "kind": kind, "model": "synthetic",
            "dataset_revision": "fixture-v1", "protocol": "test-only", "records": [row]}


class ScoringTests(unittest.TestCase):
    def test_digit_alignment_preserves_leading_zero(self):
        item = data()
        item["records"][0]["prediction"] = "12"
        report = evaluate(item)
        self.assertEqual(report["exact_match"], 0)
        self.assertEqual(report["digit_edit_errors"], 1)
        self.assertAlmostEqual(report["character_error_rate"], 1 / 3)

    def test_missing_predictions_remain_in_denominator(self):
        item = data()
        item["records"].append({"id": "b", "target": "12", "prediction": None})
        report = evaluate(item)
        self.assertEqual(report["samples"], 2)
        self.assertEqual(report["missing"], 1)
        self.assertEqual(report["exact_match"], 0.5)
        self.assertEqual(report["character_error_rate"], 2 / 5)

    def test_insertions_can_make_error_rate_above_one(self):
        item = data()
        item["records"][0].update(target="1", prediction="1111")
        self.assertEqual(evaluate(item)["character_error_rate"], 3)

    def test_arithmetic_operations_and_wrong_labels(self):
        for op, expected in (("+", 10), ("-", 4), ("*", 21)):
            item = data("arithmetic")
            item["records"][0].update(operator=op, target=expected, prediction=expected)
            self.assertEqual(evaluate(item)["exact_match"], 1)
            item["records"][0]["prediction"] = None
            self.assertEqual(evaluate(item)["exact_match"], 0)
            item["records"][0]["target"] = expected + 1
            with self.assertRaisesRegex(ValueError, "disagrees"):
                evaluate(item)

    def test_schema_and_duplicates(self):
        for kind, prediction in (("digits", True), ("digits", "१२"), ("arithmetic", True),
                                 ("arithmetic", "4")):
            item = data(kind)
            item["records"][0]["prediction"] = prediction
            with self.subTest(kind=kind, prediction=prediction), self.assertRaises(ValueError):
                evaluate(item)
        item = data()
        item["records"].append(copy.deepcopy(item["records"][0]))
        with self.assertRaisesRegex(ValueError, "duplicate"):
            evaluate(item)

    def test_cli_and_input_immutability(self):
        item = data()
        original = copy.deepcopy(item)
        evaluate(item)
        self.assertEqual(item, original)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "run.json"
            for contents, code in ((json.dumps(item), 0), ('{"kind":1,"kind":2}', 2), ('{}', 2)):
                path.write_text(contents, encoding="utf-8")
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    self.assertEqual(main([str(path)]), code)
                if code == 0:
                    self.assertEqual(json.loads(out.getvalue())["exact_match"], 1)
                else:
                    self.assertEqual(out.getvalue(), "")
                    self.assertTrue(err.getvalue())
