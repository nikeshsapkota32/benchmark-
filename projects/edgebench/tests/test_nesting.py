from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from edgebench.__main__ import main
from test_compatibility import fixture


class NestingTests(unittest.TestCase):
    def invoke(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(args)
        return code, out.getvalue(), err.getvalue()

    def test_excessive_nesting_in_every_saved_report_position(self):
        good = json.dumps(fixture())
        bad = good[:-1] + ', "private-fixture-marker": ' + '[' * 10000 + '0' + ']' * 10000 + '}'
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ("good.json", "bad.json")]
            for path, contents in zip(paths, (good, bad)):
                path.write_text(contents, encoding="utf-8")
            cases = [["--validate", str(paths[1])]]
            for mode in ("--compare", "--check-compatible"):
                for pair in (paths, paths[::-1]):
                    for audit in ([], ["--audit"]):
                        cases.append([mode, *map(str, pair), *audit])
            for args in cases:
                with self.subTest(args=args), patch("edgebench.__main__.benchmark") as runner:
                    self.assertEqual(self.invoke(args),
                                     (2, "", "edgebench: JSON nesting exceeds parser limit\n"))
                    runner.assert_not_called()

    def test_supported_nested_extras_preserve_results_and_exact_byte_audits(self):
        report = fixture()
        original = json.dumps(report)
        extra = "synthetic"
        for _ in range(20):
            extra = {"nested": [extra]}
        report["extra"] = extra
        nested = json.dumps(report)
        with tempfile.TemporaryDirectory() as directory:
            plain, extended = (Path(directory) / name for name in ("plain.json", "extended.json"))
            plain.write_text(original, encoding="utf-8")
            extended.write_text(nested, encoding="utf-8")
            self.assertEqual(self.invoke(["--validate", str(plain)]),
                             self.invoke(["--validate", str(extended)]))
            for mode in ("--compare", "--check-compatible"):
                expected = self.invoke([mode, str(plain), str(plain)])
                self.assertEqual(expected[0], 0)
                self.assertEqual(self.invoke([mode, str(plain), str(extended)]), expected)
                code, out, err = self.invoke([mode, str(plain), str(extended), "--audit"])
                self.assertEqual((code, err), (0, ""))
                audited = json.loads(out)
                self.assertEqual(audited.pop("source_sha256"), {
                    "baseline": hashlib.sha256(plain.read_bytes()).hexdigest(),
                    "candidate": hashlib.sha256(extended.read_bytes()).hexdigest(),
                })
                self.assertEqual(audited, json.loads(expected[1]))

    def test_only_decoder_recursion_errors_are_reclassified(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.json"
            path.write_text(json.dumps(fixture()), encoding="utf-8")
            for mode, target in (("--validate", "validate_report"),
                                 ("--compare", "compare_reports"),
                                 ("--check-compatible", "check_compatibility")):
                args = [mode, str(path)] + ([] if mode == "--validate" else [str(path)])
                with self.subTest(mode=mode):
                    with patch("edgebench.__main__.json.loads",
                               side_effect=RecursionError("private-fixture-marker")):
                        self.assertEqual(self.invoke(args),
                                         (2, "", "edgebench: JSON nesting exceeds parser limit\n"))
                    with patch("edgebench.__main__." + target,
                               side_effect=RecursionError("internal")):
                        with self.assertRaisesRegex(RecursionError, "internal"):
                            self.invoke(args)
