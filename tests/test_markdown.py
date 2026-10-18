from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchguard.cli import main
from benchguard.core import compare
from benchguard.report import render_markdown
from test_samples import run


class MarkdownTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.a, self.b = self.root / "a.json", self.root / "b.json"
        self.a.write_text(json.dumps(run()), encoding="utf-8")
        self.b.write_text(json.dumps(run(value=0.7)), encoding="utf-8")

    def invoke(self, *options):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main([str(self.a), str(self.b), *options])
        return code, out.getvalue(), err.getvalue()

    def test_json_default_is_unchanged(self):
        code, output, error = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(output), {"passed": False,
                         "results": [asdict(row) for row in compare(run(), run(value=0.7))]})
        self.assertEqual(error, "")

    def test_markdown_pass_and_fail_keep_exit_codes(self):
        for options, expected in (([], 1), (["--tolerance", "0.1"], 0)):
            with self.subTest(options=options):
                code, output, error = self.invoke("--format", "markdown", *options)
                self.assertEqual(code, expected)
                self.assertIn("Result: FAIL" if expected else "Result: PASS", output)
                self.assertIn("| Task | Metric | Baseline | Candidate | Status | Reason |", output)
                self.assertEqual(error, "")
                self.assertEqual(self.invoke("--format", "markdown", *options)[1], output)

    def test_hashes_identify_exact_bytes_and_override_policy(self):
        before = json.dumps(run(), indent=2).replace("\n", "\r\n").encode("utf-8")
        self.a.write_bytes(before)
        policy = self.root / "policy.json"
        policy.write_bytes(b'{"accuracy": 0.2}\n')
        code, output, error = self.invoke("--format", "markdown", "--metric-tolerances", str(policy))
        self.assertEqual((code, error), (0, ""))
        for path in (self.a, self.b, policy):
            self.assertIn(hashlib.sha256(path.read_bytes()).hexdigest(), output)
            self.assertNotIn(str(path), output)
        self.assertIn("| metric tolerances |", output)
        self.assertIn("allowed absolute degradation", output)

    def test_input_read_once_for_both_parse_and_hash(self):
        first, second = self.a.read_bytes(), self.b.read_bytes()
        with patch("benchguard.cli.Path.read_bytes", side_effect=[first, second]) as read:
            code, output, _ = self.invoke("--format", "markdown")
        self.assertEqual(code, 1)
        self.assertEqual(read.call_count, 2)
        self.assertIn(hashlib.sha256(first).hexdigest(), output)
        self.assertIn(hashlib.sha256(second).hexdigest(), output)

    def test_untrusted_metadata_cannot_create_markdown_structure(self):
        before, after = run(["secret-id-1", "secret-id-2"]), run(["secret-id-1", "secret-id-2"])
        dangerous = '|\n# injected <script> ![image](https://example.test) `code` @someone\x00\ud800'
        for item in (before, after):
            item["model"] = dangerous
            item["results"][0]["task"] = dangerous
        output = render_markdown(before, after, compare(before, after), {}, 0)
        output.encode("utf-8")  # Lone surrogate input must not break report output.
        for text in ("<script>", "![image]", "`code`", "@someone", "\n# injected", "secret-id", "\x00"):
            self.assertNotIn(text, output)
        self.assertIn("&#124;", output)
        metric_lines = output.split("## Metric results\n", 1)[1].split("Default absolute", 1)[0]
        self.assertTrue(all(line.count("|") == 7 for line in metric_lines.splitlines() if line.startswith("|")))

    def test_missing_added_and_incompatible_rows_are_visible(self):
        before, after = run(["a", "b"]), run(["a", "c"])
        before["results"].append(dict(before["results"][0], task="missing-task"))
        after["results"].append(dict(after["results"][0], task="added-task"))
        output = render_markdown(before, after, compare(before, after), {}, 0)
        for status in ("missing", "added", "incompatible"):
            self.assertIn(f"| {status} |", output)
        self.assertIn("—", output)
        self.assertIn("Result: FAIL", output)

    def test_invalid_input_produces_no_partial_markdown(self):
        for content in ('{', '{"schema_version":1,"schema_version":1}', '{}'):
            with self.subTest(content=content):
                self.b.write_text(content, encoding="utf-8")
                code, output, error = self.invoke("--format", "markdown")
                self.assertEqual(code, 2)
                self.assertEqual(output, "")
                self.assertIn("benchguard:", error)
