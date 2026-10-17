import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr

from benchguard.core import compare, failed
from benchguard.cli import main


def run(value=0.8, higher=True):
    return {"schema_version": 1, "model": "demo-v1", "dataset_revision": "fixture-v1",
            "protocol": "zero-shot-seed-42", "results": [
                {"task": "demo", "metric": "accuracy", "value": value,
                 "samples": 100, "higher_is_better": higher}]}


class ComparisonTests(unittest.TestCase):
    def test_improvement_passes(self):
        self.assertFalse(failed(compare(run(), run(.9))))

    def test_regression_fails(self):
        self.assertTrue(failed(compare(run(), run(.7))))

    def test_lower_is_better(self):
        self.assertTrue(failed(compare(run(1, False), run(2, False))))
        self.assertFalse(failed(compare(run(2, False), run(1, False))))

    def test_tolerance_boundary(self):
        self.assertFalse(failed(compare(run(.8), run(.7), .1)))
        self.assertTrue(failed(compare(run(.8), run(.69), .1)))

    def test_missing_result(self):
        candidate = run()
        candidate["results"][0]["task"] = "different-task"
        self.assertTrue(failed(compare(run(), candidate)))

    def test_changed_count_or_direction(self):
        for field, value in (("samples", 99), ("higher_is_better", False)):
            candidate = run()
            candidate["results"][0][field] = value
            self.assertEqual(compare(run(), candidate)[0].status, "incompatible")

    def test_protocol_and_revision(self):
        for field in ("protocol", "dataset_revision"):
            candidate = run()
            candidate[field] = "changed"
            with self.assertRaises(ValueError):
                compare(run(), candidate)

    def test_invalid_scores(self):
        for value in (True, None, "0.8", float("nan"), float("inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                compare(run(), run(value))

    def test_duplicates_and_empty(self):
        candidate = run()
        candidate["results"] *= 2
        with self.assertRaises(ValueError):
            compare(run(), candidate)
        candidate["results"] = []
        with self.assertRaises(ValueError):
            compare(run(), candidate)

    def test_bad_tolerance(self):
        for tolerance in (-1, float("nan"), float("inf"), True):
            with self.assertRaises(ValueError):
                compare(run(), run(), tolerance)

    def test_no_mutation(self):
        baseline = run()
        original = copy.deepcopy(baseline)
        compare(baseline, run(.9))
        self.assertEqual(baseline, original)

    def test_cli_exit_codes(self):
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder) / "a.json", Path(folder) / "b.json"
            a.write_text(json.dumps(run()))
            for contents, expected in ((json.dumps(run(.9)), 0),
                                       (json.dumps(run(.7)), 1), ("{", 2),
                                       ('{"a":1,"a":2}', 2)):
                b.write_text(contents)
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    self.assertEqual(main([str(a), str(b)]), expected)


if __name__ == "__main__":
    unittest.main()
