"""Exercise policy validation and sample identity through the same CLI run."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from benchguard.cli import main
from benchguard.core import compare
from test_samples import run


class PolicyIntegrationTests(unittest.TestCase):
    def test_metric_override_cannot_bypass_sample_identity(self):
        baseline = run(["a", "b"])
        for ids in (["a", "c"], None):
            with self.subTest(ids=ids):
                row = compare(baseline, run(ids, 0.7),
                              metric_tolerances={"accuracy": 1000})[0]
                self.assertEqual(row.status, "incompatible")
        row = compare(baseline, run(["b", "a"], 0.7),
                      metric_tolerances={"accuracy": 0.1})[0]
        self.assertEqual(row.status, "pass")

    def test_oversized_metric_override_raises_value_error(self):
        for value in (10**400, -(10**400)):
            with self.subTest(value=value), self.assertRaisesRegex(
                    ValueError, "tolerance for accuracy.*finite float range"):
                compare(run(), run(), metric_tolerances={"accuracy": value})

    def test_cli_combines_policy_identity_and_numeric_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            a, b, policy = (Path(directory) / name
                            for name in ("baseline.json", "candidate.json", "policy.json"))
            a.write_text(json.dumps(run(["a", "b"])), encoding="utf-8")
            cases = [
                (["b", "a"], 0.1, 0, "pass"),
                (["a", "c"], 1000, 1, "incompatible"),
                (None, 1000, 1, "incompatible"),
                (["a", "b"], 0, 1, "regression"),
                (["a", "b"], 10**400, 2, None),
            ]
            for ids, limit, expected, status in cases:
                with self.subTest(ids=ids, limit=limit):
                    b.write_text(json.dumps(run(ids, 0.7)), encoding="utf-8")
                    policy.write_text(json.dumps({"accuracy": limit}), encoding="utf-8")
                    output, errors = io.StringIO(), io.StringIO()
                    with redirect_stdout(output), redirect_stderr(errors):
                        code = main([str(a), str(b), "--metric-tolerances", str(policy)])
                    self.assertEqual(code, expected)
                    if expected == 2:
                        self.assertEqual(output.getvalue(), "")
                        self.assertIn("finite float range", errors.getvalue())
                        self.assertNotIn("Traceback", errors.getvalue())
                    else:
                        self.assertEqual(errors.getvalue(), "")
                        report = json.loads(output.getvalue())
                        self.assertEqual(report["passed"], expected == 0)
                        self.assertEqual(report["results"][0]["status"], status)


if __name__ == "__main__":
    unittest.main()
