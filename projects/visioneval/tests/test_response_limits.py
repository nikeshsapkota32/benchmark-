"""Exercise the declared response bound under a lower interpreter limit."""

import subprocess
import sys
import textwrap
import unittest


@unittest.skipUnless(hasattr(sys, "get_int_max_str_digits"), "configurable integer limit required")
class ResponseLimitTests(unittest.TestCase):
    def run_limited(self, code):
        completed = subprocess.run(
            [sys.executable, "-X", "int_max_str_digits=640", "-c", textwrap.dedent(code)],
            capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)

    def test_scoring_and_export_obey_policy_bound_without_changing_global_limit(self):
        self.run_limited('''
            import sys
            from visioneval import evaluate
            from visioneval.export import to_benchguard
            from visioneval.response import UnparseableResponse

            assert sys.get_int_max_str_digits() == 640
            data = {"schema_version": 1, "model": "synthetic",
                    "dataset_revision": "fixture-v1", "protocol": "synthetic",
                    "kind": "arithmetic", "records": []}
            for policy in ("numeric-text-v1", "numeric-text-count-v1"):
                for size in (640, 641, 1000):
                    # Independent arithmetic oracle, with no decimal conversion.
                    magnitude = 10 ** size - 1
                    for text, target in (("9" * size, magnitude),
                                         ("+" + "9" * size, magnitude),
                                         ("-" + "9" * size, -magnitude),
                                         ("0" * (size - 1) + "7", 7),
                                         ("-" + "0" * size, 0)):
                        row = {"id": "a", "target": target, "operands": [target, 0],
                               "operator": "+", "prediction": " \\t" + text + "\\n"}
                        data["records"] = [row]
                        report = evaluate(data, response_policy=policy)
                        exported = to_benchguard(data, response_policy=policy)
                        assert (report["correct"], report["missing"], report["samples"]) == (1, 0, 1)
                        assert exported["results"][0]["value"] == 1
                        assert all(metric["sample_ids"] == ["a"] for metric in exported["results"])
                        if policy == "numeric-text-count-v1":
                            assert report["unparseable"] == 0
                        row["prediction"] = "0" * 1001
                        for function in (evaluate, to_benchguard):
                            if policy == "numeric-text-v1":
                                try:
                                    function(data, response_policy=policy)
                                except UnparseableResponse as exc:
                                    assert "exceeds 1000 digits" in str(exc)
                                else:
                                    raise AssertionError("accepted an over-limit answer")
                            else:
                                counted = function(data, response_policy=policy)
                                rate = (counted["unparseable_rate"] if function is evaluate else
                                        counted["results"][-1]["value"])
                                assert rate == 1
                        assert sys.get_int_max_str_digits() == 640
        ''')

    def test_cli_reports_and_exports_under_low_limit(self):
        self.run_limited('''
            from contextlib import redirect_stderr, redirect_stdout
            import io
            import json
            from pathlib import Path
            import sys
            import tempfile
            from visioneval.__main__ import main

            data = {"schema_version": 1, "model": "synthetic",
                    "dataset_revision": "fixture-v1", "protocol": "synthetic",
                    "kind": "arithmetic", "records": [{"id": "a", "target": -7,
                    "operands": [-7, 0], "operator": "+", "prediction": None}]}
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "predictions.json"
                for size in (641, 1000, 1001):
                    data["records"][0]["prediction"] = "-" + "0" * (size - 1) + "7"
                    path.write_text(json.dumps(data), encoding="utf-8")
                    for policy in ("numeric-text-v1", "numeric-text-count-v1"):
                        for output_format in ("json", "benchguard"):
                            out, err = io.StringIO(), io.StringIO()
                            with redirect_stdout(out), redirect_stderr(err):
                                code = main([str(path), "--response-policy", policy,
                                             "--format", output_format])
                            if size == 1001 and policy == "numeric-text-v1":
                                assert code == 2 and out.getvalue() == ""
                                assert "record 0" in err.getvalue()
                            else:
                                assert code == 0 and err.getvalue() == ""
                                report = json.loads(out.getvalue())
                                score = (report["exact_match"] if output_format == "json" else
                                         report["results"][0]["value"])
                                assert score == (0 if size == 1001 else 1)
                            assert sys.get_int_max_str_digits() == 640
        ''')
