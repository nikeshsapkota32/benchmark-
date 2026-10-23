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


def fixture():
    return {"schema_version": 1, "splits": {
        "train": [{"id": "a", "text": "one"}, {"id": "b", "text": "two"},
                  {"id": "b", "text": "two"}],
        "test": [{"id": "a", "text": "one"}]}}


class FindingLimitTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_limits_keep_deterministic_prefix_and_full_totals(self):
        data = fixture()
        original = deepcopy(data)
        full = inspect(data)
        self.assertEqual(len(full["findings"]), 4)
        self.assertEqual(inspect(data, max_findings=None), full)
        self.assertNotIn("total_findings", full)
        for limit in (0, 1, 3, 4, 5):
            with self.subTest(limit=limit):
                report = inspect(data, max_findings=limit)
                self.assertFalse(report["passed"])
                self.assertEqual(report["findings"], full["findings"][:limit])
                self.assertEqual(report["counts"], {"test": 1, "train": 3})
                self.assertEqual(report["max_findings"], limit)
                self.assertEqual(report["total_findings"], 4)
                self.assertEqual(report["findings_truncated"], limit < 4)
                reversed_data = {**data, "splits": dict(reversed(list(data["splits"].items())))}
                self.assertEqual(inspect(reversed_data, max_findings=limit), report)
        self.assertEqual(data, original)

    def test_clean_summary_only_report_passes_without_truncation(self):
        data = {"schema_version": 1, "splits": {"test": [{"id": "a", "text": "one"}]}}
        report = inspect(data, max_findings=0)
        self.assertTrue(report["passed"])
        self.assertEqual(report["total_findings"], 0)
        self.assertEqual(report["findings"], [])
        self.assertFalse(report["findings_truncated"])

    def test_heavily_duplicated_input_retains_only_requested_findings(self):
        data = {"schema_version": 1, "splits": {
            "train": [{"id": "synthetic-id", "text": "synthetic-text"}] * 10000}}
        report = inspect(data, max_findings=2)
        self.assertEqual(len(report["findings"]), 2)
        self.assertEqual(report["total_findings"], 19998)
        self.assertEqual(report["counts"]["train"], 10000)
        self.assertFalse(report["passed"])

    def test_limits_work_with_field_mapping_and_text_policy(self):
        data = {"schema_version": 1, "splits": {"train": [
            {"key": "a", "prompt": "a b"}, {"key": " a ", "prompt": " a\tb "},
            {"key": "a", "prompt": "distinct"}]}}
        options = dict(id_field="key", text_field="prompt", text_policy="ascii-whitespace-v1")
        full = inspect(data, **options)
        report = inspect(data, max_findings=1, **options)
        self.assertEqual(report["total_findings"], 2)
        self.assertEqual(report["findings"], full["findings"][:1])
        self.assertEqual(report["fields"], full["fields"])
        self.assertEqual(report["text_policy"], full["text_policy"])

    def test_invalid_limits_fail_before_jsonl_io(self):
        for limit in (-1, True, False, 1.0, "2", [], {}):
            with self.subTest(limit=limit):
                with self.assertRaisesRegex(ValueError, "max_findings"):
                    inspect(fixture(), max_findings=limit)
                with patch.object(Path, "open") as opened:
                    with self.assertRaisesRegex(ValueError, "max_findings"):
                        inspect_jsonl({"train": "unused.jsonl"}, max_findings=limit)
                    opened.assert_not_called()

    def test_jsonl_hashes_cover_every_byte_after_limit_and_locations_match(self):
        paths, hashes = {}, {}
        for split, rows in fixture()["splits"].items():
            path = self.root / f"{split}.jsonl"
            raw = ("\r\n".join(map(json.dumps, rows)) + "\r\n").encode("utf-8")
            path.write_bytes(raw)
            paths[split] = path
            hashes[split] = hashlib.sha256(raw).hexdigest()
        full = inspect_jsonl(paths)
        for limit in (0, 1):
            report = inspect_jsonl(paths, max_findings=limit)
            self.assertEqual(report["source_sha256"], hashes)
            self.assertEqual(report["findings"], full["findings"][:limit])
            self.assertEqual(report["counts"], full["counts"])
            self.assertEqual(report["total_findings"], 4)

    def test_late_schema_and_parsing_errors_are_not_hidden(self):
        for limit in (0, 1):
            data = fixture()
            # ID already seen; text must still be validated even after the cap.
            data["splits"]["train"].append({"id": "a", "text": ""})
            with self.assertRaisesRegex(ValueError, "text"):
                inspect(data, max_findings=limit)
            path = self.root / "invalid.jsonl"
            prefix = b'{"id":"a","text":"one"}\n' * 2
            for suffix in (b"broken", b"\xff", b"\n", b'{"id":"a","id":"b"}'):
                path.write_bytes(prefix + suffix)
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    code = main(["--split", f"train={path}", "--max-findings", str(limit)])
                self.assertEqual(code, 2)
                self.assertEqual(out.getvalue(), "")
                self.assertIn(":3", err.getvalue())
            empty = self.root / "empty.jsonl"
            empty.write_bytes(b"")
            path.write_bytes(prefix)
            with self.assertRaisesRegex(ValueError, "at least one record"):
                inspect_jsonl({"a": path, "z": empty}, max_findings=limit)

    def test_cli_both_modes_fail_with_zero_retained_findings(self):
        path = self.root / "dataset.json"
        path.write_text(json.dumps(fixture()), encoding="utf-8")
        jsonl = self.root / "train.jsonl"
        jsonl.write_text("\n".join(map(json.dumps, fixture()["splits"]["train"])), encoding="utf-8")
        for args, total in (([str(path)], 4), (["--split", f"train={jsonl}"], 2)):
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(main(args + ["--max-findings", "0"]), 1)
            report = json.loads(out.getvalue())
            self.assertEqual(report["findings"], [])
            self.assertEqual(report["total_findings"], total)
            self.assertFalse(report["passed"])
            self.assertEqual(err.getvalue(), "")
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                self.assertEqual(main(args + ["--max-findings", "-1"]), 2)
