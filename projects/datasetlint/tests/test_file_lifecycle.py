from contextlib import contextmanager, redirect_stderr, redirect_stdout
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from datasetlint.__main__ import main
from datasetlint.jsonl import inspect_jsonl


class FileLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def write(self, name, payload):
        path = self.root / name
        path.write_bytes(payload)
        return path

    @contextmanager
    def tracked_files(self):
        original_open = Path.open
        opened, active = [], []

        @contextmanager
        def open_one(path, *args, **kwargs):
            if active:
                raise OSError(24, "too many simultaneously open input files")
            with original_open(path, *args, **kwargs) as stream:
                opened.append(path)
                active.append(stream)
                try:
                    yield stream
                finally:
                    active.remove(stream)

        with patch.object(Path, "open", open_one):
            yield opened, active
        self.assertEqual(active, [])

    def test_many_splits_use_one_input_descriptor_and_preserve_reports(self):
        payload = b'{"id":"same","text":"synthetic shared text"}\r\n'
        # Reverse insertion order also checks that opening follows scan order.
        paths = {f"split-{i:03}": self.write(f"{i}.jsonl", payload)
                 for i in reversed(range(64))}
        for backend in ("memory", "sqlite"):
            for limit in (None, 0, 3):
                with self.subTest(backend=backend, limit=limit):
                    expected = inspect_jsonl(paths, index_backend=backend, max_findings=limit)
                    with self.tracked_files() as (opened, active):
                        report = inspect_jsonl(paths, index_backend=backend, max_findings=limit)
                        self.assertEqual(active, [])
                    self.assertEqual(report, expected)
                    self.assertEqual(opened, [paths[name] for name in sorted(paths)])
                    self.assertEqual(report["source_sha256"],
                                     {name: hashlib.sha256(payload).hexdigest() for name in paths})
                    self.assertEqual(sum(report["counts"].values()), 64)
                    self.assertFalse(report["passed"])

    def test_parse_schema_and_empty_errors_close_current_file_without_opening_later_files(self):
        first = self.write("first.jsonl", b'{"id":"a","text":"first"}\n')
        last = self.write("last.jsonl", b'{"id":"z","text":"last"}\n')
        for backend in ("memory", "sqlite"):
            for payload in (b'not-json', b'{"id":"private"}', b''):
                with self.subTest(backend=backend, payload=payload):
                    bad = self.write("bad.jsonl", payload)
                    with self.tracked_files() as (opened, active):
                        with self.assertRaises(ValueError):
                            inspect_jsonl({"a": first, "b": bad, "c": last},
                                          index_backend=backend, max_findings=0)
                        self.assertEqual(active, [])
                    self.assertEqual(opened, [first, bad])

    def test_read_error_closes_current_file(self):
        path = self.write("read.jsonl", b'{"id":"a","text":"first"}\n')

        def broken_records(*args):
            yield {"id": "a", "text": "first"}
            raise OSError("synthetic read failure")

        with self.tracked_files() as (_, active), patch("datasetlint.jsonl._records", broken_records):
            with self.assertRaisesRegex(OSError, "synthetic read failure"):
                inspect_jsonl({"a": path})
            self.assertEqual(active, [])

    def test_late_missing_file_cli_has_no_partial_report(self):
        first = self.write("first.jsonl", b'{"id":"a","text":"first"}\n')
        missing = self.root / "missing.jsonl"
        for backend in ("memory", "sqlite"):
            out, err = io.StringIO(), io.StringIO()
            with self.tracked_files() as (opened, active), redirect_stdout(out), redirect_stderr(err):
                code = main(["--split", f"a={first}", "--split", f"b={missing}",
                             "--index-backend", backend, "--max-findings", "0"])
                self.assertEqual(active, [])
            self.assertEqual(opened, [first])
            self.assertEqual(code, 2)
            self.assertEqual(out.getvalue(), "")
            self.assertIn(str(missing), err.getvalue())


if __name__ == "__main__":
    unittest.main()
