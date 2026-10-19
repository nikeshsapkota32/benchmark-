"""Adapter entry-point regressions using synthetic aggregate exports only."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from benchguard.lm_eval_adapter import main
from test_lm_eval_adapter import convert, fixture


class LmEvalNestingTests(unittest.TestCase):
    def arguments(self, path):
        return [str(path), "--task", "toy", "--metric", "acc,none",
                "--model", "base@abc", "--dataset-revision", "dataset@abc",
                "--protocol", "prompt=v1"]

    def test_decoder_limit_returns_input_error_without_partial_export(self):
        # Beyond the supported CI interpreters' decoder limits, not a promised
        # application-level maximum depth. Construct text without json.dumps.
        nested = "[" * 10000 + "0" + "]" * 10000
        for location in ("ignored_extra", "task_config"):
            with self.subTest(location=location), tempfile.TemporaryDirectory() as directory:
                data = fixture()
                container = data if location == "ignored_extra" else data["configs"]["toy"]
                container["private-fixture-marker"] = "NESTED_PLACEHOLDER"
                payload = json.dumps(data).replace('"NESTED_PLACEHOLDER"', nested)
                path = Path(directory) / "synthetic.json"
                path.write_text(payload, encoding="utf-8")
                out, err = io.StringIO(), io.StringIO()
                with redirect_stdout(out), redirect_stderr(err):
                    status = main(self.arguments(path))
                self.assertEqual((status, out.getvalue()), (2, ""))
                self.assertEqual(err.getvalue(),
                                 "benchguard-lmeval: JSON nesting exceeds parser limit\n")

    def test_supported_nested_config_is_preserved_in_protocol(self):
        data = fixture()
        extra = "synthetic"
        for _ in range(20):
            extra = {"nested": [extra]}
        data["configs"]["toy"]["extra"] = extra
        data["ignored_extra"] = extra
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                status = main(self.arguments(path))
        self.assertEqual(status, 0)
        self.assertEqual(err.getvalue(), "")
        converted = json.loads(out.getvalue())
        self.assertEqual(converted, convert(data))
        self.assertEqual(json.loads(converted["protocol"])["task_config"]["extra"], extra)
        self.assertNotIn("ignored_extra", converted)

    def test_internal_adapter_recursion_error_is_not_hidden(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.json"
            path.write_text(json.dumps(fixture()), encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with patch("benchguard.lm_eval_adapter.adapt",
                       side_effect=RecursionError("internal-adapter-error")):
                with redirect_stdout(out), redirect_stderr(err):
                    with self.assertRaisesRegex(RecursionError, "internal-adapter-error"):
                        main(self.arguments(path))
            self.assertEqual((out.getvalue(), err.getvalue()), ("", ""))
