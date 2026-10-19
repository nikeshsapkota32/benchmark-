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


class AuditTests(unittest.TestCase):
    def run_cli(self, args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(args)
        return code, out.getvalue(), err.getvalue()

    def test_exact_bytes_same_read_and_default_output_unchanged(self):
        report = fixture()
        report["workload"] = "synthetic \u03bb fixture"
        payloads = [json.dumps(report, ensure_ascii=False).encode("utf-8"),
                    (json.dumps(report, ensure_ascii=False, indent=2) + "\n").replace("\n", "\r\n").encode("utf-8")]
        expected = dict(zip(("baseline", "candidate"),
                            (hashlib.sha256(data).hexdigest() for data in payloads)))
        self.assertNotEqual(expected["baseline"], expected["candidate"])
        for mode in ("--compare", "--check-compatible"):
            with self.subTest(mode=mode):
                # No real files: a second read fails instead of hashing different bytes.
                with patch.object(Path, "read_bytes", side_effect=payloads) as read:
                    code, out, err = self.run_cli([mode, "private-a.json", "private-b.json", "--audit"])
                self.assertEqual((code, err), (0, ""))
                self.assertEqual(read.call_count, 2)
                audited = json.loads(out)
                self.assertEqual(audited.pop("source_sha256"), expected)
                self.assertNotIn("private-", out)
                with patch.object(Path, "read_bytes", side_effect=payloads):
                    default_code, default_out, default_err = self.run_cli([mode, "a.json", "b.json"])
                self.assertEqual((default_code, default_err), (0, ""))
                self.assertEqual(audited, json.loads(default_out))
                if mode == "--compare":
                    self.assertTrue(all(row["delta_ms"] == 0 for row in audited["metrics"]))

    def test_incompatible_reports_keep_hashes_and_exit_one(self):
        before, after = fixture(), fixture()
        after["configuration"]["protocol"] = "changed"
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ("a.json", "b.json")]
            for path, report in zip(paths, (before, after)):
                path.write_text(json.dumps(report), encoding="utf-8")
            for mode in ("--compare", "--check-compatible"):
                code, out, err = self.run_cli([mode, *map(str, paths), "--audit"])
                self.assertEqual((code, err), (1, ""))
                result = json.loads(out)
                self.assertEqual(result["source_sha256"], {
                    name: hashlib.sha256(path.read_bytes()).hexdigest()
                    for name, path in zip(("baseline", "candidate"), paths)})
                if mode == "--compare":
                    self.assertEqual(result["metrics"], [])

    def test_invalid_input_emits_no_partial_audit_or_executes_work(self):
        good = json.dumps(fixture()).encode()
        for bad in (b"bad", b"\xff", b'{"x":1,"x":2}', b'{"x":NaN}', b"{}", OSError("missing")):
            for mode in ("--compare", "--check-compatible"):
                with self.subTest(bad=bad, mode=mode), patch.object(Path, "read_bytes", side_effect=[good, bad]), \
                        patch("edgebench.__main__.benchmark") as runner:
                    code, out, err = self.run_cli([mode, "a.json", "b.json", "--audit"])
                    self.assertEqual((code, out), (2, ""))
                    self.assertTrue(err)
                    runner.assert_not_called()

    def test_audit_requires_comparison_mode(self):
        for args in (["--demo", "--audit"], ["--validate", "a.json", "--audit"]):
            with patch("edgebench.__main__.benchmark") as runner, redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit) as error:
                main(args)
            self.assertEqual(error.exception.code, 2)
            runner.assert_not_called()
