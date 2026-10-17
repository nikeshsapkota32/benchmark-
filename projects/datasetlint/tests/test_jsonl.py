from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from datasetlint import inspect
from datasetlint.__main__ import main
from datasetlint.jsonl import _records, inspect_jsonl


class JsonlTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def write(self, name, rows):
        path = self.root / name
        path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8")
        return path

    def test_overlap_matches_json_and_has_physical_locations(self):
        rows = {"train": [{"id": "a", "text": "नमस्ते"}, {"id": "b", "text": "shared"}],
                "test": [{"id": "c", "text": "shared"}]}
        paths = {name: self.write(name + ".jsonl", values) for name, values in rows.items()}
        report = inspect_jsonl(paths)
        self.assertEqual(report["counts"], {"test": 1, "train": 2})
        finding = report["findings"][0]
        self.assertEqual((finding["line"], finding["first_line"]), (2, 1))
        self.assertEqual(finding["path"], str(paths["train"]))
        self.assertEqual(finding["first_path"], str(paths["test"]))
        basic = {key: value for key, value in finding.items()
                 if key not in {"path", "line", "first_path", "first_line"}}
        self.assertEqual([basic], inspect({"schema_version": 1, "splits": rows})["findings"])
        self.assertNotIn("shared", json.dumps(report))

    def test_reader_is_lazy_and_requires_only_iteration(self):
        reader = _records(iter([b'{"id":"a","text":"one"}\n', b'bad']), "data.jsonl")
        self.assertEqual(next(reader), {"id": "a", "text": "one"})
        with self.assertRaisesRegex(ValueError, r"data.jsonl:2: invalid JSON"):
            next(reader)

    def test_invalid_lines_report_path_and_line_without_content(self):
        path = self.root / "invalid.jsonl"
        first = b'{"id":"a","text":"one"}\n'
        for invalid in (b'\n', b'{"id":"private",', b'{"id":"a","id":"b"}',
                        b'{"id":"a","text":"two","extra":NaN}', b'\xff', b'[]',
                        b'{"id":"b","text":3}'):
            with self.subTest(invalid=invalid):
                path.write_bytes(first + invalid)
                with self.assertRaises(ValueError) as error:
                    inspect_jsonl({"train": path})
                self.assertIn(str(path) + ":2", str(error.exception))
                self.assertNotIn("private", str(error.exception))

    def test_empty_missing_and_bad_split_specs(self):
        path = self.write("empty.jsonl", [])
        with self.assertRaisesRegex(ValueError, "at least one record"):
            inspect_jsonl({"train": path})
        with self.assertRaises(OSError):
            inspect_jsonl({"train": self.root / "missing"})
        for mapping in ({}, {"": path}, {"train": None}):
            with self.subTest(mapping=mapping), self.assertRaises(ValueError):
                inspect_jsonl(mapping)

    def test_late_invalid_line_emits_no_partial_report(self):
        path = self.write("late.jsonl", [{"id": "a", "text": "same"}] * 2)
        path.write_text(path.read_text() + "\nnot-json", encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(main(["--split", f"train={path}"]), 2)
        self.assertEqual(out.getvalue(), "")
        self.assertIn(str(path) + ":3", err.getvalue())

    def test_cli_exit_codes_and_path_containing_equals(self):
        path = self.write("a=b.jsonl", [{"id": "a", "text": "one"}])
        cases = [(["--split", f"train={path}"], 0),
                 (["--split", f"train={path}", "--split", f"test={path}"], 1),
                 (["--split", f"train={path}", "--split", f"train={path}"], 2),
                 (["--split", "train"], 2), (["--split", "train="], 2)]
        for args, expected in cases:
            with self.subTest(args=args):
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    self.assertEqual(main(args), expected)
                if expected != 2:
                    self.assertEqual(json.loads(out.getvalue())["passed"], expected == 0)
                else:
                    self.assertEqual(out.getvalue(), "")
                    self.assertTrue(err.getvalue())

    def test_cli_rejects_mixed_input_modes(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            main(["data.json", "--split", "train=train.jsonl"])
        self.assertEqual(error.exception.code, 2)

    def test_split_argument_order_does_not_change_report(self):
        path = self.write("data.jsonl", [{"id": "a", "text": "one"}])
        self.assertEqual(inspect_jsonl({"train": path, "test": path}),
                         inspect_jsonl({"test": path, "train": path}))
