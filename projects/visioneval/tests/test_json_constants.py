from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest

from visioneval import evaluate
from visioneval.__main__ import main
from visioneval.export import to_benchguard
from test_scoring import data


class JsonConstantTests(unittest.TestCase):
    def invoke(self, contents, *options):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.json"
            path.write_text(contents, encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = main([str(path), *options])
            return code, out.getvalue(), err.getvalue()

    def assert_invalid(self, contents, *options):
        code, out, err = self.invoke(contents, *options)
        self.assertEqual((code, out), (2, ""))
        self.assertIn("nonstandard JSON constant", err)
        self.assertNotIn("private-fixture-marker", err)

    def test_constants_in_ignored_fields_fail_for_both_kinds_and_formats(self):
        for kind in ("digits", "arithmetic"):
            for token in ("NaN", "Infinity", "-Infinity"):
                for location in ("root", "record"):
                    item = data(kind)
                    holder = item if location == "root" else item["records"][0]
                    holder["private-fixture-marker"] = {"nested": ["PLACEHOLDER"]}
                    contents = json.dumps(item).replace('"PLACEHOLDER"', token)
                    for output in ("json", "benchguard"):
                        with self.subTest(kind=kind, token=token, location=location, output=output):
                            self.assert_invalid(contents, "--format", output)

    def test_late_constant_never_emits_partial_report_in_opt_in_modes(self):
        for policy in ("strict", "numeric-text-v1"):
            item = data("arithmetic")
            item["records"].append({"id": "late", "operands": [1, 2], "operator": "+",
                                    "target": 3, "prediction": 3, "extra": float("inf")})
            if policy == "numeric-text-v1":
                for record in item["records"]:
                    record["prediction"] = str(record["prediction"])
            for options in (("--details",), ("--by-operator",),
                            ("--details", "--by-operator"), ("--format", "benchguard")):
                with self.subTest(policy=policy, options=options):
                    self.assert_invalid(json.dumps(item), "--response-policy", policy, *options)

    def test_quoted_tokens_and_valid_extras_leave_outputs_unchanged(self):
        for kind in ("digits", "arithmetic"):
            item = data(kind)
            for options in ((), ("--format", "benchguard")):
                expected = self.invoke(json.dumps(item), *options)
                item["extra"] = ["NaN", "Infinity", "-Infinity", None, True, 1.25]
                item["records"][0]["extra"] = {"NaN": "not a numeric constant"}
                with self.subTest(kind=kind, options=options):
                    result = self.invoke(json.dumps(item, allow_nan=False), *options)
                    self.assertEqual(result, expected)
                    self.assertEqual(result[0], 0)

    def test_in_memory_apis_still_ignore_extra_fields(self):
        item = data()
        expected = evaluate(item), to_benchguard(item)
        item["extra"] = float("nan")
        item["records"][0]["extra"] = float("inf")
        self.assertEqual((evaluate(item), to_benchguard(item)), expected)
