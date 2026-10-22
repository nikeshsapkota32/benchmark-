"""Strict file syntax also applies to unselected synthetic export content."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from benchguard.lm_eval_adapter import main
from test_lm_eval_adapter import convert, fixture


class LmEvalJsonConstantTests(unittest.TestCase):
    def invoke(self, payload):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.json"
            path.write_text(payload, encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main([str(path), "--task", "toy", "--metric", "acc,none",
                             "--model", "base@abc", "--dataset-revision", "dataset@abc",
                             "--protocol", "prompt=v1"])
        return code, out.getvalue(), err.getvalue()

    def test_nonstandard_constants_in_selected_and_unselected_content_are_file_errors(self):
        for location in ("ignored_extra", "task_config", "unselected_metric"):
            for token in ("NaN", "Infinity", "-Infinity"):
                data = fixture()
                if location == "unselected_metric":
                    data["results"]["toy"]["acc_stderr,none"] = "PLACEHOLDER"
                else:
                    holder = data if location == "ignored_extra" else data["configs"]["toy"]
                    holder["private-fixture-marker"] = {"nested": ["PLACEHOLDER"]}
                payload = json.dumps(data).replace('"PLACEHOLDER"', token)
                with self.subTest(location=location, token=token):
                    self.assertEqual(self.invoke(payload),
                                     (2, "", "benchguard-lmeval: nonstandard JSON constant\n"))

    def test_quoted_tokens_are_preserved_in_task_metadata(self):
        data = fixture()
        extra = {"NaN": ["NaN", "Infinity", "-Infinity", None, 1.25]}
        data["configs"]["toy"]["extra"] = extra
        data["ignored_extra"] = extra
        code, output, error = self.invoke(json.dumps(data, allow_nan=False))
        self.assertEqual((code, error), (0, ""))
        converted = json.loads(output)
        self.assertEqual(converted, convert(data))
        self.assertEqual(json.loads(converted["protocol"])["task_config"]["extra"], extra)

    def test_in_memory_conversion_still_ignores_unselected_content(self):
        data = fixture()
        expected = convert(data)
        data["ignored_extra"] = float("nan")
        data["results"]["toy"]["acc_stderr,none"] = float("inf")
        self.assertEqual(convert(data), expected)
