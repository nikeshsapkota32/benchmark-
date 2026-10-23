from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from datasetlint.__main__ import main
from datasetlint.jsonl import inspect_jsonl


def record(depth):
    # Synthetic, valid JSON syntax, without recursively constructing Python data.
    return '{"id":"synthetic-id","text":"synthetic-text","extra":' + '[' * depth + '0' + ']' * depth + '}'


class NestingTests(unittest.TestCase):
    def test_cli_deep_json_and_jsonl_fail_without_partial_output(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            for backend in ("memory", "sqlite"):
                for mode in ("json", "jsonl"):
                    with self.subTest(backend=backend, mode=mode):
                        payload = record(10000)
                        if mode == "json":
                            payload = '{"schema_version":1,"splits":{"train":[' + payload + ']}}'
                        else:
                            # Already-found duplicates must not produce a partial report.
                            payload = record(0) + '\n' + record(0) + '\n' + payload
                        path.write_text(payload, encoding="utf-8")
                        args = [str(path)] if mode == "json" else ["--split", f"train={path}"]
                        out, err = io.StringIO(), io.StringIO()
                        with redirect_stdout(out), redirect_stderr(err):
                            code = main(args + ["--index-backend", backend, "--max-findings", "0"])
                        self.assertEqual((code, out.getvalue()), (2, ""))
                        self.assertIn("JSON nesting exceeds parser limit", err.getvalue())
                        self.assertNotIn("synthetic-id", err.getvalue())
                        self.assertNotIn("Traceback", err.getvalue())
                        if mode == "jsonl":
                            self.assertIn(f"{path}:3:", err.getvalue())

    def test_jsonl_api_closes_failed_input_and_never_opens_later_split(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "deep.jsonl"
            path.write_text(record(0) + '\n' + record(10000), encoding="utf-8")
            original_open = Path.open
            for backend in ("memory", "sqlite"):
                handles, opened = [], []

                def tracked_open(current, *args, **kwargs):
                    opened.append(current)
                    stream = original_open(current, *args, **kwargs)
                    handles.append(stream)
                    return stream

                with self.subTest(backend=backend), patch.object(Path, "open", tracked_open):
                    with self.assertRaisesRegex(ValueError, "deep.jsonl:2: JSON nesting exceeds parser limit"):
                        inspect_jsonl({"a": path, "z": Path(directory) / "not-opened.jsonl"},
                                      index_backend=backend)
                    self.assertEqual(opened, [path])
                    self.assertTrue(handles)
                    self.assertTrue(all(handle.closed for handle in handles))

    def test_decoder_recursion_details_are_not_echoed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.jsonl"
            path.write_text(record(0), encoding="utf-8")
            with patch("datasetlint.jsonl.json.loads", side_effect=RecursionError("private detail")):
                with self.assertRaises(ValueError) as caught:
                    inspect_jsonl({"train": path})
            self.assertEqual(str(caught.exception), f"{path}:1: JSON nesting exceeds parser limit")

    def test_supported_nested_extras_remain_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            for mode in ("json", "jsonl"):
                payload = record(20)
                if mode == "json":
                    payload = '{"schema_version":1,"splits":{"train":[' + payload + ']}}'
                path.write_text(payload, encoding="utf-8")
                args = [str(path)] if mode == "json" else ["--split", f"train={path}"]
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    self.assertEqual(main(args), 0)
                self.assertEqual(err.getvalue(), "")
                report = json.loads(out.getvalue())
                self.assertTrue(report["passed"])
                self.assertEqual(report["counts"], {"train": 1})
