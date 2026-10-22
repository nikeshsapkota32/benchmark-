from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from benchguard.cli import _load_with_digest, load, main
from benchguard.core import compare
from test_core import run


class JsonConstantTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.paths = [Path(directory.name) / name for name in
                      ("baseline.json", "candidate.json", "tolerances.json", "directions.json")]
        self.originals = [json.dumps(run()), json.dumps(run()),
                          '{"accuracy": 0.01}', '{"accuracy": true}']
        self.reset_inputs()

    def reset_inputs(self):
        for path, contents in zip(self.paths, self.originals):
            path.write_text(contents, encoding="utf-8")

    def invoke(self, output):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main([str(self.paths[0]), str(self.paths[1]),
                         "--metric-tolerances", str(self.paths[2]),
                         "--metric-directions", str(self.paths[3]), "--format", output])
        return code, out.getvalue(), err.getvalue()

    def assert_rejected(self):
        for output in ("json", "json-audit", "markdown"):
            with self.subTest(output=output):
                self.assertEqual(self.invoke(output),
                                 (2, "", "benchguard: nonstandard JSON constant\n"))

    def test_ignored_run_fields_cannot_hide_nonstandard_constants(self):
        for index in (0, 1):
            for location in ("root", "result"):
                for token in ("NaN", "Infinity", "-Infinity"):
                    self.reset_inputs()
                    item = run()
                    holder = item if location == "root" else item["results"][0]
                    holder["private-fixture-marker"] = {"nested": ["PLACEHOLDER"]}
                    content = json.dumps(item).replace('"PLACEHOLDER"', token)
                    self.paths[index].write_text(content, encoding="utf-8")
                    with self.subTest(input=index, location=location, token=token):
                        self.assert_rejected()

    def test_scores_and_both_policy_files_reject_constants_before_comparison(self):
        for token in ("NaN", "Infinity", "-Infinity"):
            for index in range(4):
                self.reset_inputs()
                item = run("PLACEHOLDER") if index < 2 else {"accuracy": "PLACEHOLDER"}
                content = json.dumps(item).replace('"PLACEHOLDER"', token)
                self.paths[index].write_text(content, encoding="utf-8")
                with self.subTest(input=index, token=token):
                    self.assert_rejected()

    def test_load_helpers_reject_top_level_and_nested_constants(self):
        for token in ("NaN", "Infinity", "-Infinity"):
            for content in (token, '{"extra": [' + token + ']}'):
                self.paths[0].write_text(content, encoding="utf-8")
                for loader in (load, _load_with_digest):
                    with self.subTest(content=content, loader=loader.__name__):
                        with self.assertRaisesRegex(ValueError, "^nonstandard JSON constant$"):
                            loader(self.paths[0])

    def test_quoted_tokens_and_valid_extras_preserve_results_and_exact_byte_audits(self):
        expected = json.loads(self.invoke("json")[1])
        item = run()
        item["extra"] = {"NaN": ["NaN", "Infinity", "-Infinity", None, True, 1.25]}
        item["results"][0]["extra"] = {"Infinity": -2}
        payload = (json.dumps(item, indent=2, allow_nan=False) + "\r\n").encode("utf-8")
        self.paths[1].write_bytes(payload)
        self.assertEqual(_load_with_digest(self.paths[1]), (item, hashlib.sha256(payload).hexdigest()))
        for output in ("json", "json-audit", "markdown"):
            with self.subTest(output=output):
                code, report, error = self.invoke(output)
                self.assertEqual((code, error), (0, ""))
                if output == "markdown":
                    self.assertIn(hashlib.sha256(payload).hexdigest(), report)
                else:
                    parsed = json.loads(report)
                    self.assertEqual({key: parsed[key] for key in ("passed", "results")}, expected)
                    if output == "json-audit":
                        self.assertEqual(parsed["source_sha256"]["candidate"],
                                         hashlib.sha256(payload).hexdigest())

    def test_in_memory_comparison_still_ignores_extra_fields(self):
        before, after = run(), run()
        expected = compare(before, after)
        before["extra"] = float("nan")
        after["results"][0]["extra"] = float("inf")
        self.assertEqual(compare(before, after), expected)

    def test_valid_json_large_exponents_still_use_existing_field_validation(self):
        # 1e400 is valid JSON syntax, unlike Infinity. Extra-field semantics are ignored.
        content = self.originals[1][:-1] + ', "extra": 1e400}'
        self.paths[1].write_text(content, encoding="utf-8")
        for output in ("json", "json-audit", "markdown"):
            self.assertEqual(self.invoke(output)[0], 0)
        self.paths[1].write_text(json.dumps(run("PLACEHOLDER")).replace('"PLACEHOLDER"', '1e400'),
                                 encoding="utf-8")
        code, report, error = self.invoke("json-audit")
        self.assertEqual((code, report), (2, ""))
        self.assertIn("value must be a finite number", error)
