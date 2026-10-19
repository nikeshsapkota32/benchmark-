from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


script = Path(__file__).resolve().parents[1] / "scripts" / "profile_indexes.py"
spec = importlib.util.spec_from_file_location("profile_indexes", script)
profiler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profiler)


class IndexProfilingTests(unittest.TestCase):
    def test_generator_is_repeatable_and_preserves_text_size(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            left = profiler.write_synthetic(a, 21, 64)
            right = profiler.write_synthetic(b, 21, 64)
            for split, count in (("train", 21), ("test", 3)):
                raw = left[split].read_bytes()
                self.assertEqual(raw, right[split].read_bytes())
                rows = [json.loads(line) for line in raw.splitlines()]
                self.assertEqual(len(rows), count)
                self.assertTrue(all(len(row["text"].encode("ascii")) == 64 for row in rows))

    @unittest.skipUnless(sys.platform == "linux", "Linux ru_maxrss semantics")
    def test_small_real_workers_agree_and_report_explicit_units(self):
        result = profiler.profile(21, 64, 2)
        self.assertEqual(result["experiment"], "datasetlint-synthetic-index-profile-v1")
        self.assertEqual(result["validation_report"]["total_findings"], 6)
        self.assertEqual(result["validation_report"]["findings"], [])
        self.assertEqual([row["backend"] for row in result["runs"]], ["memory", "sqlite", "sqlite", "memory"])
        self.assertEqual([row["trial"] for row in result["runs"]], [1, 1, 2, 2])
        for row in result["runs"]:
            self.assertGreater(row["peak_rss_bytes"], 0)
            self.assertGreaterEqual(row["elapsed_seconds"], 0)
            self.assertNotIn("report", row)
            for direction in ("input", "output"):
                self.assertIs(type(row["filesystem_operations"][direction]), int)
                self.assertGreaterEqual(row["filesystem_operations"][direction], 0)
        self.assertEqual(set(result["implementation_sha256"]), {"datasetlint", "datasetlint.indexes", "datasetlint.jsonl"})
        self.assertEqual(len(result["script_sha256"]), 64)
        self.assertIn("process-lifetime", result["measurement"]["memory"])
        self.assertIn("ru_inblock", result["measurement"]["io"])

    @unittest.skipUnless(sys.platform == "linux", "Linux resource counters")
    def test_io_counts_cover_scan_and_cleanup_not_process_lifetime(self):
        import resource
        events = []
        def usage(who):
            self.assertEqual(who, resource.RUSAGE_SELF)
            events.append("usage")
            if len(events) == 1:
                return SimpleNamespace(ru_inblock=100, ru_oublock=200, ru_maxrss=10)
            return SimpleNamespace(ru_inblock=103, ru_oublock=207, ru_maxrss=20)
        def scan(*args, **kwargs):
            events.append("scan")
            # inspect_jsonl returns only after its index context has cleaned up.
            return {"synthetic": True}
        with patch.object(resource, "getrusage", side_effect=usage), \
                patch.object(profiler.jsonl, "inspect_jsonl", side_effect=scan), \
                patch.object(profiler.time, "perf_counter", side_effect=[5.0, 5.5]):
            result = profiler.measure({}, "sqlite")
        self.assertEqual(events, ["usage", "scan", "usage"])
        self.assertEqual(result["filesystem_operations"], {"input": 3, "output": 7})
        self.assertEqual(result["elapsed_seconds"], 0.5)
        self.assertEqual(result["peak_rss_bytes"], 20 * 1024)
        self.assertEqual(result["report"], {"synthetic": True})

    @unittest.skipUnless(sys.platform == "linux", "Linux resource counters")
    def test_zero_io_counters_are_valid(self):
        import resource
        usage = SimpleNamespace(ru_inblock=99, ru_oublock=42, ru_maxrss=10)
        with patch.object(resource, "getrusage", return_value=usage), \
                patch.object(profiler.jsonl, "inspect_jsonl", return_value={}):
            result = profiler.measure({}, "memory")
        self.assertEqual(result["filesystem_operations"], {"input": 0, "output": 0})

    def test_non_linux_is_rejected_instead_of_guessing_units(self):
        with patch.object(profiler.sys, "platform", "darwin"):
            with self.assertRaisesRegex(ValueError, "Linux only"):
                profiler.profile()
            with self.assertRaisesRegex(ValueError, "Linux only"):
                profiler.measure({}, "memory")

    def test_invalid_workload_sizes_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for records, size in ((0, 512), (True, 512), (10, 0), (10, True)):
                with self.subTest(records=records, size=size), self.assertRaises(ValueError):
                    profiler.write_synthetic(directory, records, size)
        with patch.object(profiler.sys, "platform", "linux"):
            for trials in (0, True, -1):
                with self.assertRaises(ValueError):
                    profiler.profile(trials=trials)

    def test_worker_failure_returns_no_partial_output(self):
        with patch.object(profiler.sys, "platform", "linux"), patch.object(
                profiler.subprocess, "run", return_value=subprocess.CompletedProcess([], 2, "", "private detail")):
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = profiler.main(["--records", "10", "--trials", "1"])
        self.assertEqual((code, out.getvalue()), (2, ""))
        self.assertNotIn("private detail", err.getvalue())

    def test_report_mismatch_discards_resource_results(self):
        def completed(report):
            return subprocess.CompletedProcess([], 0, json.dumps({"report": report}), "")
        with patch.object(profiler.sys, "platform", "linux"), patch.object(
                profiler.subprocess, "run", side_effect=[completed({"a": 1}), completed({"a": 2})]):
            with self.assertRaisesRegex(ValueError, "backend reports differ"):
                profiler.profile(10, 32, 1)
