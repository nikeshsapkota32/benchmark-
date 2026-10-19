from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchguard.cli import _load_with_digest, load, main
from test_core import run


class NestingTests(unittest.TestCase):
    def test_each_input_returns_exit_two_without_partial_output(self):
        nested = '[' * 10000 + '0' + ']' * 10000
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in
                     ("baseline.json", "candidate.json", "tolerances.json", "directions.json")]
            originals = [json.dumps(run()), json.dumps(run(.7)),
                         '{"accuracy": 0.01}', '{"accuracy": true}']
            for index, path in enumerate(paths):
                for target, contents in zip(paths, originals):
                    target.write_text(contents, encoding="utf-8")
                # Deep extras in runs and deep values in policies must both fail at decoding.
                contents = (originals[index][:-1] + ', "private-fixture-marker": '
                            + nested + '}')
                path.write_text(contents, encoding="utf-8")
                for output in ("json", "json-audit", "markdown"):
                    with self.subTest(input=path.name, output=output):
                        out, err = io.StringIO(), io.StringIO()
                        with redirect_stdout(out), redirect_stderr(err):
                            code = main([str(paths[0]), str(paths[1]),
                                         "--metric-tolerances", str(paths[2]),
                                         "--metric-directions", str(paths[3]), "--format", output])
                        self.assertEqual((code, out.getvalue()), (2, ""))
                        self.assertEqual(err.getvalue(), "benchguard: JSON nesting exceeds parser limit\n")

    def test_load_api_raises_value_error_for_decoder_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.json"
            path.write_text('[' * 10000 + '0' + ']' * 10000, encoding="utf-8")
            for loader in (load, _load_with_digest):
                with self.subTest(loader=loader.__name__):
                    with self.assertRaisesRegex(ValueError, "^JSON nesting exceeds parser limit$"):
                        loader(path)

    def test_supported_nested_extras_preserve_data_and_exact_byte_digest(self):
        item = run()
        extra = "synthetic"
        for _ in range(20):
            extra = {"nested": [extra]}
        item["extra"] = extra
        payload = (json.dumps(item, indent=2) + '\r\n').encode("utf-8")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.json"
            path.write_bytes(payload)
            self.assertEqual(_load_with_digest(path), (item, hashlib.sha256(payload).hexdigest()))
            self.assertEqual(load(path), item)
            for output in ("json", "json-audit", "markdown"):
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    self.assertEqual(main([str(path), str(path), "--format", output]), 0)

    def test_decoder_message_is_sanitized_without_hiding_comparison_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.json"
            path.write_text(json.dumps(run()), encoding="utf-8")
            with patch("benchguard.cli.json.loads", side_effect=RecursionError("private-marker")):
                with self.assertRaisesRegex(ValueError, "^JSON nesting exceeds parser limit$"):
                    load(path)
            with patch("benchguard.cli.compare", side_effect=RecursionError("internal")):
                with self.assertRaisesRegex(RecursionError, "internal"):
                    main([str(path), str(path)])
