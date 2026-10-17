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


POLICY = "ascii-whitespace-v1"


def fixture():
    return {"schema_version": 1, "splits": {
        "train": [{"id": "synthetic/a", "text": "alpha beta"}],
        "test": [{"id": "synthetic/b", "text": " alpha\t beta\n"}]}}


class TextPolicyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_exact_default_and_explicit_exact_leave_report_unchanged(self):
        expected = {"schema_version": 1, "passed": True,
                    "counts": {"test": 1, "train": 1}, "findings": []}
        self.assertEqual(inspect(fixture()), expected)
        self.assertEqual(inspect(fixture(), text_policy="exact"), expected)

    def test_all_six_ascii_whitespace_characters_and_first_occurrence(self):
        data = fixture()
        whitespace = " \t\r\n\v\f"
        data["splits"]["test"] = [{"id": str(index), "text": char + "alpha" + char * 2 + "beta" + char}
                                  for index, char in enumerate(whitespace)]
        original = deepcopy(data)
        report = inspect(data, text_policy=POLICY)
        self.assertEqual(data, original)
        self.assertFalse(report["passed"])
        self.assertEqual(report["text_policy"], POLICY)
        self.assertEqual(report["findings"], [
            {"code": "duplicate_text", "split": "test", "index": index,
             "first_split": "test", "first_index": 0} for index in range(1, 6)] + [
            {"code": "overlap_text", "split": "train", "index": 0,
             "first_split": "test", "first_index": 0}])
        self.assertNotIn("alpha", json.dumps(report))
        self.assertNotIn("synthetic/a", json.dumps(report))
        data["splits"] = dict(reversed(list(data["splits"].items())))
        self.assertEqual(inspect(data, text_policy=POLICY), report)

    def test_ids_stay_exact_and_custom_text_fields_are_normalized(self):
        data = {"schema_version": 1, "splits": {"train": [
            {"sample_id": "a b", "prompt": " same\ttext "},
            {"sample_id": " a\tb ", "prompt": "same text"},
            {"sample_id": "a b", "prompt": "different"}]}}
        report = inspect(data, id_field="sample_id", text_field="prompt", text_policy=POLICY)
        self.assertEqual(report["fields"], {"id": "sample_id", "text": "prompt"})
        self.assertEqual([f["code"] for f in report["findings"]], ["duplicate_text", "duplicate_id"])
        self.assertEqual([f["index"] for f in report["findings"]], [1, 2])

    def test_unicode_case_punctuation_and_no_whitespace_are_not_normalized(self):
        values = ["alpha beta", "alphabeta", "Alpha beta", "alpha-beta",
                  "alpha\u00a0beta", "alpha\u2003beta", "alpha\u200bbeta",
                  "\u00a0alpha beta\u00a0", "caf\u00e9", "cafe\u0301"]
        data = {"schema_version": 1, "splits": {"train": [
            {"id": str(index), "text": value} for index, value in enumerate(values)]}}
        report = inspect(data, text_policy=POLICY)
        self.assertTrue(report["passed"])
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["text_policy"], POLICY)

    def test_invalid_policies_fail_before_opening_jsonl_files(self):
        for value in (None, True, 1, [], {}, "", "unicode", "EXACT"):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "text_policy"):
                    inspect(fixture(), text_policy=value)
                with patch.object(Path, "open") as opened, self.assertRaisesRegex(ValueError, "text_policy"):
                    inspect_jsonl({"train": "unused.jsonl"}, text_policy=value)
                opened.assert_not_called()

    def test_jsonl_retains_raw_hashes_and_original_locations(self):
        data = fixture()
        paths, hashes = {}, {}
        for split, rows in data["splits"].items():
            raw = ("\n".join(map(json.dumps, rows)) + "\r\n").encode("utf-8")
            path = self.root / (split + ".jsonl")
            path.write_bytes(raw)
            paths[split] = path
            hashes[split] = hashlib.sha256(raw).hexdigest()
        exact = inspect_jsonl(paths)
        report = inspect_jsonl(paths, text_policy=POLICY)
        self.assertEqual(report.pop("source_sha256"), hashes)
        self.assertEqual(exact["source_sha256"], hashes)
        self.assertTrue(exact["passed"])
        finding = report["findings"][0]
        self.assertEqual(finding.pop("path"), str(paths["train"]))
        self.assertEqual(finding.pop("first_path"), str(paths["test"]))
        self.assertEqual(finding.pop("line"), 1)
        self.assertEqual(finding.pop("first_line"), 1)
        self.assertEqual(report, inspect(data, text_policy=POLICY))

    def test_cli_both_modes_default_exact_and_opt_in_exit_codes(self):
        data = fixture()
        path = self.root / "dataset.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        jsonl_args = []
        for split, rows in data["splits"].items():
            split_path = self.root / (split + ".jsonl")
            split_path.write_text("\n".join(map(json.dumps, rows)), encoding="utf-8")
            jsonl_args.extend(["--split", f"{split}={split_path}"])
        for args in ([str(path)], jsonl_args):
            for flags, expected in (([], 0), (["--text-policy", "exact"], 0),
                                    (["--text-policy", POLICY], 1)):
                with self.subTest(args=args, flags=flags):
                    out, err = io.StringIO(), io.StringIO()
                    with redirect_stdout(out), redirect_stderr(err):
                        self.assertEqual(main(args + flags), expected)
                    report = json.loads(out.getvalue())
                    self.assertEqual(report.get("text_policy", "exact"), POLICY if expected else "exact")
                    self.assertEqual(err.getvalue(), "")
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            main([str(path), "--text-policy", "guess"])
        self.assertEqual(error.exception.code, 2)

    def test_late_invalid_records_still_reject_without_partial_report(self):
        data = fixture()
        for value in (" \t\r\n\v\f", "\u00a0", None, 3):
            data["splits"]["train"].append({"id": "bad", "text": value})
            with self.assertRaises(ValueError):
                inspect(data, text_policy=POLICY)
            data["splits"]["train"].pop()
        path = self.root / "input.jsonl"
        rows = [data["splits"]["test"][0], data["splits"]["train"][0]]
        path.write_text("\n".join(map(json.dumps, rows)) + "\nnot-json", encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(main(["--split", f"train={path}", "--text-policy", POLICY]), 2)
        self.assertEqual(out.getvalue(), "")
        self.assertIn(":3:", err.getvalue())
