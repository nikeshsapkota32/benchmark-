import copy
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from benchguard.cli import main
from benchguard.core import compare, failed
from test_tolerances import mixed_run


class DirectionPolicyTests(unittest.TestCase):
    def test_policy_catches_shared_wrong_direction(self):
        baseline, candidate = mixed_run(), mixed_run(latency=120)
        for run in (baseline, candidate):
            run["results"][1]["higher_is_better"] = True
        self.assertFalse(failed(compare(baseline, candidate)))
        with self.assertRaisesRegex(ValueError, "baseline direction conflicts"):
            compare(baseline, candidate, metric_directions={"latency_ms": False})

    def test_valid_policy_preserves_scores_tolerances_and_inputs(self):
        baseline, candidate = mixed_run(), mixed_run(accuracy=0.79, latency=105)
        directions, tolerances = {"accuracy": True, "latency_ms": False}, {"accuracy": 0.01, "latency_ms": 5}
        original = copy.deepcopy((baseline, candidate, directions, tolerances))
        expected = compare(baseline, candidate, metric_tolerances=tolerances)
        self.assertEqual(expected, compare(baseline, candidate, metric_directions=directions,
                                           metric_tolerances=tolerances))
        self.assertFalse(failed(expected))
        self.assertEqual((baseline, candidate, directions, tolerances), original)
        self.assertTrue(failed(compare(baseline, candidate, metric_directions=directions)))

    def test_conflicting_candidate_and_added_tasks_are_checked(self):
        for added in (False, True):
            candidate = mixed_run()
            if added:
                candidate["results"].append(dict(candidate["results"][1], task="extra", higher_is_better=True))
            else:
                candidate["results"][1]["higher_is_better"] = True
            with self.subTest(added=added), self.assertRaisesRegex(ValueError, "candidate direction conflicts"):
                compare(mixed_run(), candidate, tolerance=1000, metric_directions={"latency_ms": False})

    def test_invalid_policy_values_and_unknown_metrics(self):
        policies = [[], 1, "accuracy", {"": True}, {1: True}, {"unknown": True}]
        policies += [{"accuracy": value} for value in (0, 1, None, "true", [], {})]
        for policy in policies:
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                compare(mixed_run(), mixed_run(), metric_directions=policy)
        candidate = mixed_run()
        candidate["results"].append(dict(candidate["results"][0], metric="new"))
        with self.assertRaisesRegex(ValueError, "unknown baseline metric"):
            compare(mixed_run(), candidate, metric_directions={"new": True})

    def test_empty_and_partial_policies_keep_existing_behavior(self):
        baseline, candidate = mixed_run(), mixed_run(latency=110)
        expected = compare(baseline, candidate)
        for policy in (None, {}, {"accuracy": True}):
            self.assertEqual(compare(baseline, candidate, metric_directions=policy), expected)

    def test_policy_does_not_bypass_identity_or_missing_results(self):
        baseline = mixed_run()
        for change in ("missing", "samples", "sample_ids"):
            candidate = mixed_run()
            if change == "missing":
                candidate["results"].pop(0)
            elif change == "samples":
                candidate["results"][0]["samples"] = 99
            else:
                candidate["results"][0]["sample_ids"] = [str(i) for i in range(100)]
            with self.subTest(change=change):
                self.assertTrue(failed(compare(baseline, candidate, metric_directions={"accuracy": True})))

    def test_cli_hash_and_error_output_in_both_formats(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            baseline, candidate, policy = [root / name for name in ("a.json", "b.json", "policy.json")]
            baseline.write_text(json.dumps(mixed_run()), encoding="utf-8")
            candidate.write_text(json.dumps(mixed_run(latency=120)), encoding="utf-8")
            cases = [(' {"latency_ms": false}\n', 1), ('{"latency_ms": true}', 2),
                     ('{"latency_ms": 0}', 2), ('{"latency_ms":false,"latency_ms":false}', 2),
                     ('null', 2), ('[]', 2), ('{', 2), ('{"typo":true}', 2)]
            for content, expected in cases:
                policy.write_text(content, encoding="utf-8")
                for format_name in ("json", "markdown"):
                    with self.subTest(content=content, format=format_name):
                        out, err = io.StringIO(), io.StringIO()
                        with redirect_stdout(out), redirect_stderr(err):
                            code = main([str(baseline), str(candidate), "--metric-directions", str(policy),
                                         "--format", format_name])
                        self.assertEqual(code, expected)
                        if expected == 2:
                            self.assertEqual(out.getvalue(), "")
                            self.assertTrue(err.getvalue())
                        elif format_name == "markdown":
                            self.assertIn("metric directions", out.getvalue())
                            self.assertIn(hashlib.sha256(content.encode()).hexdigest(), out.getvalue())
                        else:
                            self.assertEqual(set(json.loads(out.getvalue())), {"passed", "results"})
