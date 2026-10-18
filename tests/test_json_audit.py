from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchguard.cli import main
from benchguard.core import compare
from benchguard.report import build_json_audit
from test_samples import run


class JsonAuditTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.a, self.b = self.root / "baseline.json", self.root / "candidate.json"
        self.a.write_text(json.dumps(run()), encoding="utf-8")
        self.b.write_text(json.dumps(run(value=0.7)), encoding="utf-8")

    def invoke(self, *options):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main([str(self.a), str(self.b), *options])
        return code, out.getvalue(), err.getvalue()

    def test_versioned_envelope_preserves_default_json_results_and_exit_codes(self):
        for flags, expected in (([], 1), (["--tolerance", "0.2"], 0)):
            with self.subTest(flags=flags):
                code, default, error = self.invoke(*flags)
                self.assertEqual((code, error), (expected, ""))
                self.assertEqual(self.invoke("--format", "json", *flags)[1], default)
                code, output, error = self.invoke("--format", "json-audit", *flags)
                self.assertEqual((code, error), (expected, ""))
                report = json.loads(output)
                self.assertEqual({key: report[key] for key in ("passed", "results")}, json.loads(default))
                self.assertEqual(set(json.loads(default)), {"passed", "results"})
                self.assertEqual(report["schema_version"], 1)
                self.assertEqual(report["report_type"], "benchguard-comparison")
                self.assertEqual(report["policy"], {"tolerance": 0.2 if flags else 0.0,
                                                    "metric_tolerances": {}, "metric_directions": {}})
                self.assertEqual(set(report["source_sha256"]), {"baseline", "candidate"})

    def test_exact_byte_hashes_and_both_reviewed_policies_are_included(self):
        self.a.write_bytes(json.dumps(run(), indent=2).replace("\n", "\r\n").encode("utf-8"))
        tolerances, directions = self.root / "tolerance.json", self.root / "direction.json"
        tolerances.write_bytes(b'{"accuracy": 0.2}\n')
        directions.write_bytes(b'{"accuracy": true}\r\n')
        args = ["--format", "json-audit", "--tolerance", "0.01", "--metric-tolerances", str(tolerances),
                "--metric-directions", str(directions)]
        code, output, error = self.invoke(*args)
        self.assertEqual((code, error), (0, ""))
        report = json.loads(output)
        self.assertEqual(report["policy"], {"tolerance": 0.01, "metric_tolerances": {"accuracy": 0.2},
                                            "metric_directions": {"accuracy": True}})
        paths = {"baseline": self.a, "candidate": self.b,
                 "metric_tolerances": tolerances, "metric_directions": directions}
        self.assertEqual(report["source_sha256"],
                         {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in paths.items()})
        for path in paths.values():
            self.assertNotIn(str(path), output)
        self.assertEqual(self.invoke(*args)[1], output)
        self.a.write_bytes(self.a.read_bytes() + b"\n")
        changed = json.loads(self.invoke(*args)[1])
        self.assertNotEqual(changed["source_sha256"]["baseline"], report["source_sha256"]["baseline"])
        self.assertEqual(changed["results"], report["results"])

    def test_metadata_is_preserved_without_extra_fields_or_raw_sample_ids(self):
        data = run(["synthetic-sensitive-a", "synthetic-sensitive-b"])
        metadata = 'नमस्ते |\n<script>\ud800'
        data["model"] = metadata
        data["private_extension"] = "do-not-copy"
        self.a.write_text(json.dumps(data), encoding="utf-8")
        data["model"] = "candidate-model"
        self.b.write_text(json.dumps(data), encoding="utf-8")
        code, output, error = self.invoke("--format", "json-audit")
        self.assertEqual((code, error), (0, ""))
        output.encode("utf-8")
        report = json.loads(output)
        self.assertEqual(report["runs"]["baseline"], {"model": metadata,
                         "dataset_revision": data["dataset_revision"], "protocol": data["protocol"]})
        self.assertEqual(report["runs"]["candidate"]["model"], "candidate-model")
        self.assertNotIn("synthetic-sensitive", output)
        self.assertNotIn("do-not-copy", output)
        self.assertIsNotNone(report["results"][0]["baseline_sample_fingerprint"])

    def test_files_are_read_once_for_parsing_and_hashing(self):
        before, after = self.a.read_bytes(), self.b.read_bytes()
        raw = [b'{"accuracy": true}', b'{"accuracy": 0.2}', before, after]
        with patch("benchguard.cli.Path.read_bytes", side_effect=raw) as read:
            code, output, error = self.invoke("--format", "json-audit", "--metric-directions", "direction",
                                               "--metric-tolerances", "tolerance")
        self.assertEqual((code, error, read.call_count), (0, "", 4))
        self.assertEqual(set(json.loads(output)["source_sha256"].values()),
                         {hashlib.sha256(item).hexdigest() for item in raw})

    def test_empty_supplied_policy_is_distinguishable_from_absent_file(self):
        path = self.root / "empty-policy.json"
        path.write_text("{}", encoding="utf-8")
        default = json.loads(self.invoke("--format", "json-audit")[1])
        supplied = json.loads(self.invoke("--format", "json-audit", "--metric-tolerances", str(path))[1])
        self.assertEqual(default["policy"], supplied["policy"])
        self.assertNotIn("metric_tolerances", default["source_sha256"])
        self.assertEqual(supplied["source_sha256"]["metric_tolerances"], hashlib.sha256(b"{}").hexdigest())

    def test_report_builder_does_not_mutate_or_alias_policy_inputs(self):
        data, overrides, directions = run(), {"accuracy": 0.1}, {"accuracy": True}
        original = deepcopy((data, overrides, directions))
        report = build_json_audit(data, data, compare(data, data), {}, 0.0, overrides, directions)
        self.assertEqual((data, overrides, directions), original)
        report["policy"]["metric_tolerances"]["accuracy"] = 9
        report["policy"]["metric_directions"]["accuracy"] = False
        report["runs"]["baseline"]["model"] = "changed"
        self.assertEqual((data, overrides, directions), original)

    def test_malformed_inputs_and_policy_conflicts_emit_no_partial_audit(self):
        for content in ('{', '{"schema_version":1,"schema_version":1}', '{}'):
            self.b.write_text(content, encoding="utf-8")
            code, output, error = self.invoke("--format", "json-audit")
            self.assertEqual((code, output), (2, ""))
            self.assertIn("benchguard:", error)
        self.b.write_text(json.dumps(run()), encoding="utf-8")
        path = self.root / "wrong-direction.json"
        path.write_text('{"accuracy": false}', encoding="utf-8")
        code, output, error = self.invoke("--format", "json-audit", "--metric-directions", str(path))
        self.assertEqual((code, output), (2, ""))
        self.assertTrue(error)

    def test_missing_added_and_incompatible_results_keep_statuses(self):
        before, after = run(["a", "b"]), run(["a", "c"])
        before["results"].append(dict(before["results"][0], task="missing-task"))
        after["results"].append(dict(after["results"][0], task="added-task"))
        self.a.write_text(json.dumps(before), encoding="utf-8")
        self.b.write_text(json.dumps(after), encoding="utf-8")
        code, output, error = self.invoke("--format", "json-audit")
        self.assertEqual((code, error), (1, ""))
        report = json.loads(output)
        self.assertFalse(report["passed"])
        self.assertEqual({row["status"] for row in report["results"]}, {"missing", "added", "incompatible"})
