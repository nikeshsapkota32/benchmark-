"""Synthetic, offline contract tests between two independently installed CLIs."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


def digits():
    return {"schema_version": 1, "model": "synthetic-baseline",
            "dataset_revision": "synthetic-v1", "protocol": "fixture-only",
            "kind": "digits", "records": [
                {"id": "a", "target": "007", "prediction": "007"},
                {"id": "b", "target": "3", "prediction": "3"}]}


class VisionEvalBenchGuardCliTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def invoke(self, module, *args):
        return subprocess.run([sys.executable, "-m", module, *map(str, args)],
                              capture_output=True, text=True, timeout=30)

    def export(self, name, data, policy="strict"):
        source = self.root / (name + "-predictions.json")
        source.write_text(json.dumps(data), encoding="utf-8")
        result = self.invoke("visioneval", source, "--format", "benchguard",
                             "--response-policy", policy)
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        destination = self.root / (name + "-run.json")
        destination.write_text(result.stdout, encoding="utf-8")
        return destination

    def compare(self, baseline, candidate):
        return self.invoke("benchguard.cli", baseline, candidate, "--format", "json-audit")

    def assert_incompatible(self, before, after, policy="strict"):
        baseline = self.export("baseline", before)
        candidate = self.export("candidate", after, policy)
        result = self.compare(baseline, candidate)
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertIn("incompatible protocol", result.stderr)

    def test_reordered_records_and_new_model_pass_with_auditable_sources(self):
        before = digits()
        after = deepcopy(before)
        after["model"] = "synthetic-candidate"
        after["records"].reverse()
        baseline = self.export("baseline", before)
        candidate = self.export("candidate", after)
        result = self.compare(baseline, candidate)
        self.assertEqual((result.returncode, result.stderr), (0, ""))
        report = json.loads(result.stdout)
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual(report["report_type"], "benchguard-comparison")
        self.assertTrue(report["passed"])
        self.assertEqual(len(report["results"]), 2)
        for row in report["results"]:
            self.assertIsNotNone(row["baseline_sample_fingerprint"])
            self.assertEqual(row["baseline_sample_fingerprint"], row["candidate_sample_fingerprint"])
        self.assertEqual(report["runs"]["candidate"]["model"], "synthetic-candidate")
        self.assertEqual(report["source_sha256"], {
            "baseline": hashlib.sha256(baseline.read_bytes()).hexdigest(),
            "candidate": hashlib.sha256(candidate.read_bytes()).hexdigest()})

    def test_missing_prediction_stays_in_denominator_and_fails_both_metrics(self):
        before = digits()
        after = deepcopy(before)
        after["records"][0]["prediction"] = None
        baseline = self.export("baseline", before)
        candidate = self.export("candidate", after)
        exported = json.loads(candidate.read_text(encoding="utf-8"))
        for metric in exported["results"]:
            self.assertEqual(metric["samples"], 2)
            self.assertEqual(metric["sample_ids"], ["a", "b"])
        result = self.compare(baseline, candidate)
        self.assertEqual((result.returncode, result.stderr), (1, ""))
        report = json.loads(result.stdout)
        self.assertFalse(report["passed"])
        rows = {row["metric"]: row for row in report["results"]}
        self.assertEqual(set(rows), {"exact_match", "character_error_rate"})
        self.assertEqual({row["status"] for row in rows.values()}, {"regression"})
        self.assertEqual(rows["exact_match"]["candidate"], 0.5)
        self.assertEqual(rows["character_error_rate"]["candidate"], 0.75)

    def test_changed_labels_with_identical_scores_are_incompatible(self):
        before = digits()
        after = deepcopy(before)
        after["records"][0].update(target="009", prediction="009")
        self.assert_incompatible(before, after)

    def test_changed_arithmetic_problem_with_same_answer_is_incompatible(self):
        before = digits()
        before.update(kind="arithmetic", records=[
            {"id": "a", "operands": [2, 3], "operator": "+", "target": 5, "prediction": 5}])
        after = deepcopy(before)
        after["records"][0].update(operands=[6, 1], operator="-")
        self.assert_incompatible(before, after)

    def test_response_policy_changes_are_incompatible_even_when_scores_match(self):
        self.assert_incompatible(digits(), digits(), policy="numeric-text-v1")

    def test_counting_policy_is_incompatible_with_rejecting_policy(self):
        baseline = self.export("baseline", digits(), "numeric-text-v1")
        candidate = self.export("candidate", digits(), "numeric-text-count-v1")
        result = self.compare(baseline, candidate)
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertIn("incompatible protocol", result.stderr)

    def test_unparseable_rate_regression_is_visible_with_unchanged_accuracy(self):
        before = digits()
        before.update(kind="arithmetic", records=[
            {"id": "a", "operands": [2, 3], "operator": "+", "target": 5, "prediction": "4"}])
        after = deepcopy(before)
        after["records"][0]["prediction"] = "synthetic explanation: 5"
        baseline = self.export("baseline", before, "numeric-text-count-v1")
        candidate = self.export("candidate", after, "numeric-text-count-v1")
        result = self.compare(baseline, candidate)
        self.assertEqual((result.returncode, result.stderr), (1, ""))
        rows = {row["metric"]: row for row in json.loads(result.stdout)["results"]}
        self.assertEqual(rows["exact_match"]["baseline"], 0.0)
        self.assertEqual(rows["exact_match"]["candidate"], 0.0)
        self.assertEqual(rows["unparseable_rate"]["baseline"], 0.0)
        self.assertEqual(rows["unparseable_rate"]["candidate"], 1.0)
        self.assertEqual(rows["unparseable_rate"]["status"], "regression")
        self.assertEqual(rows["unparseable_rate"]["baseline_sample_fingerprint"],
                         rows["unparseable_rate"]["candidate_sample_fingerprint"])

    def test_invalid_later_record_produces_no_partial_export(self):
        data = digits()
        data["records"][1]["target"] = "not-a-digit"
        source = self.root / "invalid.json"
        source.write_text(json.dumps(data), encoding="utf-8")
        result = self.invoke("visioneval", source, "--format", "benchguard")
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertIn("visioneval:", result.stderr)
