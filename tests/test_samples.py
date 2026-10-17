import copy
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from benchguard.cli import main
from benchguard.core import compare, failed
from benchguard.samples import sample_fingerprint


def run(ids=None, value=0.8):
    entry = {"task": "demo", "metric": "accuracy", "samples": 2,
             "value": value, "higher_is_better": True}
    if ids is not None:
        entry["sample_ids"] = ids
    return {"schema_version": 1, "model": "synthetic", "dataset_revision": "fixture-v1",
            "protocol": "test-only", "results": [entry]}


class SampleIdentityTests(unittest.TestCase):
    def test_equal_counts_different_samples_fail(self):
        rows = compare(run(["a", "b"]), run(["a", "c"]))
        self.assertTrue(failed(rows))
        self.assertEqual(rows[0].reason, "sample IDs differ")
        self.assertNotEqual(rows[0].baseline_sample_fingerprint,
                            rows[0].candidate_sample_fingerprint)

    def test_order_does_not_change_identity(self):
        rows = compare(run(["a", "b"]), run(["b", "a"]))
        self.assertFalse(failed(rows))
        self.assertEqual(rows[0].baseline_sample_fingerprint,
                         rows[0].candidate_sample_fingerprint)
        self.assertEqual(len(rows[0].baseline_sample_fingerprint), 64)

    def test_one_sided_identity_is_incompatible(self):
        for baseline, candidate in ((run(), run(["a", "b"])),
                                    (run(["a", "b"]), run())):
            with self.subTest(baseline=baseline):
                self.assertEqual(compare(baseline, candidate)[0].status, "incompatible")

    def test_legacy_runs_remain_comparable(self):
        row = compare(run(), run())[0]
        self.assertEqual(row.status, "pass")
        self.assertIsNone(row.baseline_sample_fingerprint)
        self.assertIsNone(row.candidate_sample_fingerprint)

    def test_invalid_ids_are_rejected(self):
        for ids in (None, [], "ab", [1, 2], [True, "b"], ["", "b"],
                    [" ", "b"], ["a", "a"], [["a"], "b"]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                sample_fingerprint(ids)
        candidate = run()
        candidate["results"][0]["sample_ids"] = None
        with self.assertRaises(ValueError):
            compare(run(), candidate)

    def test_sample_count_must_match(self):
        with self.assertRaisesRegex(ValueError, "length must equal samples"):
            compare(run(["a"]), run(["a"]))

    def test_id_boundaries_and_unicode_are_preserved(self):
        self.assertNotEqual(sample_fingerprint(["a,b", "c"]),
                            sample_fingerprint(["a", "b,c"]))
        self.assertNotEqual(sample_fingerprint(["a\nb", "c"]),
                            sample_fingerprint(["a", "b\nc"]))
        self.assertEqual(sample_fingerprint(["नमस्ते", "café"]),
                         sample_fingerprint(["café", "नमस्ते"]))
        self.assertNotEqual(sample_fingerprint(["a", "b"]),
                            sample_fingerprint([" a", "b"]))

    def test_matching_ids_do_not_hide_regressions(self):
        self.assertTrue(failed(compare(run(["a", "b"]), run(["b", "a"], 0.7))))

    def test_tolerance_does_not_hide_changed_samples(self):
        self.assertTrue(failed(compare(run(["a", "b"]), run(["a", "c"]), 1)))

    def test_inputs_are_not_mutated(self):
        baseline, candidate = run(["b", "a"]), run(["a", "b"])
        original = copy.deepcopy((baseline, candidate))
        compare(baseline, candidate)
        self.assertEqual((baseline, candidate), original)

    def test_cli_outputs_fingerprints_and_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / "a.json", Path(directory) / "b.json"
            a.write_text(json.dumps(run(["private-id-1", "private-id-2"])), encoding="utf-8")
            for ids, expected in ((["private-id-2", "private-id-1"], 0),
                                  (["private-id-1", "private-id-3"], 1),
                                  (["private-id-1"], 2)):
                b.write_text(json.dumps(run(ids)), encoding="utf-8")
                output, errors = io.StringIO(), io.StringIO()
                with redirect_stdout(output), redirect_stderr(errors):
                    code = main([str(a), str(b)])
                self.assertEqual(code, expected)
                self.assertNotIn("private-id", output.getvalue())
                if expected == 2:
                    self.assertEqual(output.getvalue(), "")
                else:
                    report = json.loads(output.getvalue())
                    self.assertEqual(report["passed"], expected == 0)
                    self.assertEqual(len(report["results"][0]["baseline_sample_fingerprint"]), 64)


if __name__ == "__main__":
    unittest.main()
