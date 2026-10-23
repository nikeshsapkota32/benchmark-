from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from datasetlint.__main__ import main
from datasetlint.jsonl import inspect_jsonl


class SourceHashTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def test_exact_bytes_include_unicode_line_endings_and_final_newline(self):
        path = self.root / "input.jsonl"
        row = '{"id":"a","text":"नमस्ते"}'.encode("utf-8")
        hashes = []
        for raw in (row, row + b"\n", row + b"\r\n", b" " + row + b" \n"):
            path.write_bytes(raw)
            report = inspect_jsonl({"train": path})
            self.assertTrue(report["passed"])
            self.assertEqual(report["source_sha256"], {"train": hashlib.sha256(raw).hexdigest()})
            hashes.append(report["source_sha256"]["train"])
        self.assertEqual(len(set(hashes)), 4)

    def test_hashes_are_keyed_by_split_and_cover_all_records(self):
        a, b = self.root / "a.jsonl", self.root / "b.jsonl"
        raw = b'{"sample_id":"a","prompt":"one"}\n{"sample_id":"b","prompt":"two"}'
        a.write_bytes(raw)
        b.write_bytes(raw)
        report = inspect_jsonl({"train": a, "test": b}, id_field="sample_id", text_field="prompt")
        self.assertFalse(report["passed"])
        self.assertEqual(list(report["source_sha256"]), ["test", "train"])
        self.assertEqual(report["source_sha256"], dict.fromkeys(("test", "train"), hashlib.sha256(raw).hexdigest()))
        self.assertEqual(report, inspect_jsonl({"test": b, "train": a}, id_field="sample_id", text_field="prompt"))

    def test_hashing_uses_the_same_single_stream_as_parsing(self):
        raw = b'{"id":"a","text":"one"}\n{"id":"b","text":"two"}\n'
        # No read/seek interface: hashing must follow the parser's iteration.
        class Stream:
            def __enter__(self):
                return iter(raw.splitlines(keepends=True))

            def __exit__(self, *args):
                pass

        with patch.object(Path, "open", return_value=Stream()) as opened:
            report = inspect_jsonl({"train": "virtual.jsonl"})
        opened.assert_called_once_with("rb")
        self.assertEqual(report["source_sha256"]["train"], hashlib.sha256(raw).hexdigest())
        self.assertEqual(report["counts"], {"train": 2})

    def test_cli_emits_hashes_only_after_all_inputs_validate(self):
        path = self.root / "input.jsonl"
        raw = b'{"id":"a","text":"one"}\n'
        for payload, code in ((raw, 0), (raw * 2, 1), (raw * 2 + b"broken", 2)):
            path.write_bytes(payload)
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                self.assertEqual(main(["--split", f"train={path}"]), code)
            if code == 2:
                self.assertEqual(out.getvalue(), "")
                self.assertIn(":3", err.getvalue())
            else:
                self.assertEqual(json.loads(out.getvalue())["source_sha256"],
                                 {"train": hashlib.sha256(payload).hexdigest()})
                self.assertEqual(err.getvalue(), "")
