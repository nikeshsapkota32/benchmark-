from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from datasetlint.__main__ import main


class JsonConstantTests(unittest.TestCase):
    def run_input(self, content, *, jsonl=False, backend="memory"):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.json"
            path.write_text(content, encoding="utf-8")
            args = ["--split", "train=" + str(path)] if jsonl else [str(path)]
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main(args + ["--index-backend", backend, "--max-findings", "0"])
            return code, out.getvalue(), err.getvalue()

    def test_nonstandard_constants_in_ignored_record_fields_fail_in_both_modes(self):
        for constant in ("NaN", "Infinity", "-Infinity"):
            row = '{"id":"private-id","text":"private-text","extra":{"values":[' + constant + ']}}'
            wrapped = '{"schema_version":1,"splits":{"train":[' + row + ']}}'
            for backend in ("memory", "sqlite"):
                for jsonl, content in ((False, wrapped), (True, row)):
                    with self.subTest(constant=constant, backend=backend, jsonl=jsonl):
                        code, out, err = self.run_input(content, jsonl=jsonl, backend=backend)
                        self.assertEqual((code, out), (2, ""))
                        self.assertIn("nonfinite JSON number", err)
                        self.assertNotIn("private", err)

    def test_nonstandard_constants_in_top_level_metadata_fail(self):
        for constant in ("NaN", "Infinity", "-Infinity"):
            content = ('{"schema_version":1,"splits":{"train":[{"id":"a","text":"one"}]},'
                       '"extra":' + constant + '}')
            with self.subTest(constant=constant):
                code, out, err = self.run_input(content)
                self.assertEqual((code, out), (2, ""))
                self.assertIn("nonfinite JSON number", err)

    def test_late_constant_never_emits_earlier_duplicate_findings(self):
        row = '{"id":"a","text":"same"}'
        late = '{"id":"b","text":"other","extra":NaN}'
        for jsonl, content in ((False, '{"schema_version":1,"splits":{"train":[' +
                               ','.join((row, row, late)) + ']}}'),
                              (True, '\n'.join((row, row, late)))):
            with self.subTest(jsonl=jsonl):
                code, out, err = self.run_input(content, jsonl=jsonl)
                self.assertEqual((code, out), (2, ""))
                self.assertIn("nonfinite JSON number", err)

    def test_quoted_names_and_valid_extra_values_remain_accepted(self):
        row = {"id": "NaN", "text": "Infinity -Infinity", "extra":
               {"NaN": [None, True, False, 1.5, -2, "NaN", "Infinity", "-Infinity"]}}
        for jsonl, content in ((False, json.dumps({"schema_version": 1, "splits": {"train": [row]}})),
                              (True, json.dumps(row))):
            for backend in ("memory", "sqlite"):
                with self.subTest(jsonl=jsonl, backend=backend):
                    code, out, err = self.run_input(content, jsonl=jsonl, backend=backend)
                    self.assertEqual((code, err), (0, ""))
                    self.assertTrue(json.loads(out)["passed"])
