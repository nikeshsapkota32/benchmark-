import copy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from benchguard.cli import main
from benchguard.core import compare, failed


def mixed_run(accuracy=0.8, latency=100.0):
    return {
        "schema_version": 1,
        "model": "synthetic",
        "dataset_revision": "fixture-v1",
        "protocol": "test-only",
        "results": [
            {"task": "demo", "metric": "accuracy", "value": accuracy,
             "samples": 100, "higher_is_better": True},
            {"task": "demo", "metric": "latency_ms", "value": latency,
             "samples": 100, "higher_is_better": False},
        ],
    }


class MetricToleranceTests(unittest.TestCase):
    def test_mixed_units_and_directions(self):
        limits = {"accuracy": 0.01, "latency_ms": 5}
        before = mixed_run()
        rows = compare(before, mixed_run(0.79, 105), metric_tolerances=limits)
        self.assertFalse(failed(rows))
        self.assertEqual(rows[1].reason, "allowed absolute degradation: 5")
        self.assertTrue(failed(compare(before, mixed_run(0.78, 105), metric_tolerances=limits)))
        self.assertTrue(failed(compare(before, mixed_run(0.79, 106), metric_tolerances=limits)))

    def test_unlisted_metric_uses_default(self):
        candidate = mixed_run(0.79, 105)
        self.assertFalse(failed(compare(mixed_run(), candidate, 0.01,
                                       metric_tolerances={"latency_ms": 5})))
        self.assertTrue(failed(compare(mixed_run(), candidate, 0,
                                      metric_tolerances={"latency_ms": 5})))

    def test_zero_override_tightens_permissive_default(self):
        rows = compare(mixed_run(), mixed_run(0.79), 10,
                       metric_tolerances={"accuracy": 0})
        self.assertEqual(rows[0].status, "regression")

    def test_override_applies_across_tasks(self):
        baseline, candidate = mixed_run(), mixed_run()
        extra = dict(baseline["results"][0], task="second")
        baseline["results"].append(extra)
        candidate["results"].append(dict(extra, value=0.79))
        self.assertFalse(failed(compare(baseline, candidate,
                                       metric_tolerances={"accuracy": 0.01})))

    def test_invalid_overrides_are_rejected(self):
        invalid = [[], 1, "accuracy", {"accurracy": 1}, {"": 1}, {1: 1}]
        invalid.extend({"accuracy": v} for v in (-1, True, None, "1", float("inf"), float("nan")))
        for limits in invalid:
            with self.subTest(limits=limits), self.assertRaises(ValueError):
                compare(mixed_run(), mixed_run(), metric_tolerances=limits)

    def test_only_baseline_metrics_can_have_overrides(self):
        candidate = mixed_run()
        candidate["results"].append(dict(candidate["results"][0], metric="new_metric"))
        with self.assertRaisesRegex(ValueError, "unknown baseline metric"):
            compare(mixed_run(), candidate, metric_tolerances={"new_metric": 0.1})

    def test_tolerances_do_not_bypass_compatibility_or_missing_results(self):
        for change in ("missing", "samples", "higher_is_better"):
            candidate = mixed_run()
            if change == "missing":
                candidate["results"].pop(0)
            else:
                candidate["results"][0][change] = 99 if change == "samples" else False
            self.assertTrue(failed(compare(mixed_run(), candidate,
                                          metric_tolerances={"accuracy": 1000})))

    def test_inputs_are_unchanged(self):
        baseline, candidate, limits = mixed_run(), mixed_run(0.79), {"accuracy": 0.01}
        original = copy.deepcopy((baseline, candidate, limits))
        compare(baseline, candidate, metric_tolerances=limits)
        self.assertEqual((baseline, candidate, limits), original)

    def test_cli_policy_and_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline, candidate, policy = (root / name for name in ("a.json", "b.json", "policy.json"))
            baseline.write_text(json.dumps(mixed_run()), encoding="utf-8")
            candidate.write_text(json.dumps(mixed_run(0.79, 105)), encoding="utf-8")
            cases = [
                ('{"accuracy": 0.01, "latency_ms": 5}', 0),
                ('{"accuracy": 0.01, "latency_ms": 4}', 1),
                ('{"accuracy": 1, "accuracy": 0}', 2),
                ('{"accurracy": 1}', 2),
                ('{"accuracy": NaN}', 2),
                ('{"accuracy": -1}', 2),
                ('[]', 2), ('null', 2), ('{', 2),
            ]
            for contents, expected in cases:
                with self.subTest(contents=contents):
                    policy.write_text(contents, encoding="utf-8")
                    output, errors = io.StringIO(), io.StringIO()
                    with redirect_stdout(output), redirect_stderr(errors):
                        code = main([str(baseline), str(candidate), "--metric-tolerances", str(policy)])
                    self.assertEqual(code, expected)
                    if expected == 2:
                        self.assertEqual(output.getvalue(), "")
                        self.assertIn("benchguard:", errors.getvalue())
                    else:
                        self.assertEqual(json.loads(output.getvalue())["passed"], expected == 0)
            policy.unlink()
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main([str(baseline), str(candidate), "--metric-tolerances", str(policy)]), 2)


if __name__ == "__main__":
    unittest.main()
