from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from visioneval.__main__ import main
from test_scoring import data


class NestingTests(unittest.TestCase):
    def invoke(self, contents, *options):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.json"
            path.write_text(contents, encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main([str(path), *options])
            return code, out.getvalue(), err.getvalue()

    def test_excessive_nesting_fails_without_report_or_export(self):
        for kind in ("digits", "arithmetic"):
            for policy in ("strict", "numeric-text-v1"):
                item = data(kind)
                if policy == "numeric-text-v1":
                    for record in item["records"]:
                        if record["prediction"] is not None:
                            record["prediction"] = str(record["prediction"])
                # The ignored field follows valid records; no partial output is allowed.
                contents = (json.dumps(item)[:-1] + ', "private-fixture-marker": '
                            + '[' * 10000 + '0' + ']' * 10000 + '}')
                modes = [(), ("--details",), ("--format", "benchguard")]
                if kind == "arithmetic":
                    modes.append(("--details", "--by-operator"))
                for options in modes:
                    with self.subTest(kind=kind, policy=policy, options=options):
                        code, out, err = self.invoke(contents, "--response-policy", policy, *options)
                        self.assertEqual((code, out), (2, ""))
                        self.assertEqual(err, "visioneval: JSON nesting exceeds parser limit\n")

    def test_supported_nested_extras_preserve_both_outputs(self):
        for kind in ("digits", "arithmetic"):
            item = data(kind)
            original = json.dumps(item)
            extra = "synthetic"
            for _ in range(20):
                extra = {"nested": [extra]}
            item["extra"] = extra
            for options in ((), ("--details",), ("--format", "benchguard")):
                with self.subTest(kind=kind, options=options):
                    expected = self.invoke(original, *options)
                    self.assertEqual(expected[0], 0)
                    self.assertEqual(self.invoke(json.dumps(item), *options), expected)

    def test_decoder_error_is_sanitized_but_evaluator_errors_are_not_reclassified(self):
        contents = json.dumps(data())
        with patch("visioneval.__main__.json.loads",
                   side_effect=RecursionError("private-fixture-marker")):
            self.assertEqual(self.invoke(contents),
                             (2, "", "visioneval: JSON nesting exceeds parser limit\n"))
        with patch("visioneval.__main__.evaluate", side_effect=RecursionError("internal")):
            with self.assertRaisesRegex(RecursionError, "internal"):
                self.invoke(contents)
