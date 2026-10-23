from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from datasetlint import inspect
from datasetlint.__main__ import main
from datasetlint.jsonl import inspect_jsonl


ZERO = {"duplicate_id": 0, "duplicate_text": 0, "overlap_id": 0, "overlap_text": 0}


def fixture():
    return {"schema_version": 1, "splits": {
        "a": [{"id": "one", "text": "first"}, {"id": "two", "text": "second"},
              {"id": "two", "text": "second"}],
        "b": [{"id": "one", "text": "first"}, {"id": "one", "text": "third"}]}}


class FindingSummaryTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def cli(self, args):
        with redirect_stdout(io.StringIO()) as stdout, redirect_stderr(io.StringIO()) as stderr:
            code = main(args)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_full_scan_categories_ignore_retention_and_keep_first_occurrence_semantics(self):
        data = fixture()
        original = deepcopy(data)
        expected = {"duplicate_id": 1, "duplicate_text": 1, "overlap_id": 2, "overlap_text": 1}
        for backend in ("memory", "sqlite"):
            full = inspect(data, index_backend=backend)
            for limit in (None, 0, 1, 4, 5, 10):
                with self.subTest(backend=backend, limit=limit):
                    options = dict(index_backend=backend, max_findings=limit)
                    default = inspect(data, **options)
                    report = inspect(data, include_summary=True, **options)
                    self.assertEqual(report.pop("finding_counts"), expected)
                    self.assertEqual(report, default)
                    self.assertEqual(report["findings"], full["findings"][:limit])
                    self.assertFalse(report["passed"])
                    if limit is not None:
                        self.assertEqual(sum(expected.values()), report["total_findings"])
                    reversed_data = {**data, "splits": dict(reversed(list(data["splits"].items())))}
                    self.assertEqual(inspect(reversed_data, include_summary=True, **options),
                                     {**report, "finding_counts": expected})
        self.assertEqual(data, original)

    def test_clean_report_has_all_zero_categories_and_default_shape_is_unchanged(self):
        data = {"schema_version": 1, "splits": {"test": [{"id": "a", "text": "unique"}]}}
        for backend in ("memory", "sqlite"):
            default = inspect(data, index_backend=backend)
            self.assertNotIn("finding_counts", default)
            self.assertEqual(inspect(data, include_summary=False, index_backend=backend), default)
            summary = inspect(data, include_summary=True, index_backend=backend)
            self.assertEqual(summary.pop("finding_counts"), ZERO)
            self.assertEqual(summary, default)
            self.assertTrue(summary["passed"])

    def test_jsonl_custom_fields_and_policy_keep_all_hashes_and_locations(self):
        rows = {"a": [{"key": "1", "prompt": "a b"}, {"key": "2", "prompt": "a\tb"}],
                "b": [{"key": "1", "prompt": " a b "}]}
        paths, hashes = {}, {}
        for split, records in rows.items():
            raw = ("\r\n".join(map(json.dumps, records)) + "\r\n").encode("utf-8")
            paths[split] = self.root / (split + ".jsonl")
            paths[split].write_bytes(raw)
            hashes[split] = hashlib.sha256(raw).hexdigest()
        for backend in ("memory", "sqlite"):
            for policy, expected in (("exact", {**ZERO, "overlap_id": 1}),
                                     ("ascii-whitespace-v1", {**ZERO, "duplicate_text": 1,
                                                            "overlap_id": 1, "overlap_text": 1})):
                options = dict(id_field="key", text_field="prompt", text_policy=policy,
                               index_backend=backend)
                full = inspect_jsonl(paths, **options)
                for limit in (0, 1, None):
                    with self.subTest(backend=backend, policy=policy, limit=limit):
                        report = inspect_jsonl(paths, include_summary=True, max_findings=limit, **options)
                        self.assertEqual(report["finding_counts"], expected)
                        self.assertEqual(report["source_sha256"], hashes)
                        self.assertEqual(report["findings"], full["findings"][:limit])
                        self.assertEqual(report["counts"], full["counts"])

    def test_invalid_summary_option_fails_before_opening_input_or_indexes(self):
        for value in (None, 0, 1, "true", [], {}):
            with self.subTest(value=value), patch("datasetlint.open_indexes") as indexed:
                with self.assertRaisesRegex(ValueError, "include_summary"):
                    inspect(fixture(), include_summary=value)
                indexed.assert_not_called()
                with patch.object(Path, "open") as opened:
                    with self.assertRaisesRegex(ValueError, "include_summary"):
                        inspect_jsonl({"a": "unused.jsonl"}, include_summary=value)
                    opened.assert_not_called()

    def test_cli_both_formats_keep_failure_status_with_zero_details(self):
        data = fixture()
        path = self.root / "dataset.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        jsonl_args = []
        for name, rows in data["splits"].items():
            split = self.root / (name + ".jsonl")
            split.write_text("\n".join(map(json.dumps, rows)), encoding="utf-8")
            jsonl_args += ["--split", f"{name}={split}"]
        for args in ([str(path)], jsonl_args):
            for backend in ("memory", "sqlite"):
                code, stdout, stderr = self.cli(args + ["--summary", "--max-findings", "0",
                                                       "--index-backend", backend])
                self.assertEqual((code, stderr), (1, ""))
                report = json.loads(stdout)
                self.assertEqual(report["finding_counts"],
                                 {"duplicate_id": 1, "duplicate_text": 1, "overlap_id": 2, "overlap_text": 1})
                self.assertEqual(report["total_findings"], 5)
                self.assertEqual(report["findings"], [])

    def test_late_bad_records_never_emit_partial_summary(self):
        for backend in ("memory", "sqlite"):
            data = fixture()
            data["splits"]["b"].append({"id": "one", "text": ""})
            path = self.root / "dataset.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            code, stdout, stderr = self.cli([str(path), "--summary", "--max-findings", "0",
                                             "--index-backend", backend])
            self.assertEqual((code, stdout), (2, ""))
            self.assertIn("text", stderr)
            path = self.root / "late.jsonl"
            for suffix in (b'broken', b'\xff', b'{"id":"one","text":""}'):
                path.write_bytes(b'{"id":"one","text":"first"}\n' * 2 + suffix)
                code, stdout, stderr = self.cli(["--split", f"a={path}", "--summary",
                                                 "--max-findings", "0", "--index-backend", backend])
                self.assertEqual((code, stdout), (2, ""))
                self.assertIn(":3", stderr)

    def test_summary_counts_occurrences_not_pairs_or_affected_records(self):
        data = {"schema_version": 1, "splits": {
            "a": [{"id": "same", "text": "same"}] * 100}}
        report = inspect(data, include_summary=True, max_findings=0)
        self.assertEqual(report["finding_counts"], {**ZERO, "duplicate_id": 99, "duplicate_text": 99})
        self.assertEqual(report["total_findings"], 198)
        self.assertEqual(report["counts"], {"a": 100})


if __name__ == "__main__":
    unittest.main()
