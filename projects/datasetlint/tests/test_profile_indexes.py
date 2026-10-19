from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sqlite3
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
            if row["backend"] == "memory":
                self.assertIsNone(row["index_storage"])
            else:
                storage = row["index_storage"]
                self.assertGreater(storage["logical_database_bytes"], 0)
                self.assertEqual(storage["logical_database_bytes"],
                                 storage["page_count"] * storage["page_size_bytes"])
                self.assertIn("database", storage["files"])
                self.assertTrue(storage["uncommitted_transaction"])
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
            with profiler.datasetlint.open_indexes("sqlite") as (ids, texts):
                ids["a"] = ("train", 0)
            # inspect_jsonl returns only after its index context has cleaned up.
            return {"synthetic": True}
        snapshot = profiler.storage_snapshot
        def observe(connection):
            events.append("storage")
            return snapshot(connection)
        with patch.object(resource, "getrusage", side_effect=usage), \
                patch.object(profiler.jsonl, "inspect_jsonl", side_effect=scan), \
                patch.object(profiler.time, "perf_counter", side_effect=[5.0, 5.5]), \
                patch.object(profiler, "storage_snapshot", side_effect=observe):
            result = profiler.measure({}, "sqlite")
        self.assertEqual(events, ["usage", "scan", "storage", "usage"])
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

    def test_snapshot_accounts_for_sidecars_and_unavailable_allocation(self):
        class Connection:
            in_transaction = True
            def execute(self, query):
                if query == "PRAGMA database_list":
                    return [(0, "main", "/private/index.sqlite")]
                return SimpleNamespace(fetchone=lambda: (3 if "count" in query else 4096,))
        stats = {"index.sqlite": SimpleNamespace(st_size=8192, st_blocks=16),
                 "index.sqlite-journal": SimpleNamespace(st_size=100, st_blocks=8),
                 "index.sqlite-wal": SimpleNamespace(st_size=50)}
        def stat(path):
            if path.name not in stats:
                raise FileNotFoundError(path)
            return stats[path.name]
        with patch.object(Path, "stat", stat):
            result = profiler.storage_snapshot(Connection())
        self.assertEqual(result["logical_database_bytes"], 12288)
        self.assertEqual(result["file_bytes"], 8342)
        self.assertEqual(result["files"]["journal"]["allocated_bytes"], 4096)
        self.assertIsNone(result["allocated_bytes"])
        self.assertNotIn("shm", result["files"])
        self.assertNotIn("/private", json.dumps(result))
        stats["index.sqlite-wal"].st_blocks = 0
        with patch.object(Path, "stat", stat):
            self.assertEqual(profiler.storage_snapshot(Connection())["allocated_bytes"], 12288)

    def test_snapshot_does_not_commit_buffered_database_pages(self):
        with profiler.indexes.open_indexes("sqlite") as (ids, texts):
            for i in range(20):
                ids[str(i) + "x" * 2000] = ("train", i)
            connection = ids.connection
            before = connection.execute("PRAGMA page_count").fetchone()[0]
            result = profiler.storage_snapshot(connection)
            self.assertTrue(connection.in_transaction)
            self.assertEqual(result["page_count"], before)
            self.assertEqual(connection.execute("SELECT count(*) FROM seen").fetchone()[0], 20)
            # Buffered logical pages are not the database file's on-disk length.
            self.assertGreater(result["logical_database_bytes"], result["files"]["database"]["file_bytes"])

    @unittest.skipUnless(sys.platform == "linux", "Linux profiling")
    def test_observation_and_failure_both_close_connection_and_restore_hook(self):
        original = profiler.datasetlint.open_indexes
        snapshot = profiler.storage_snapshot
        for fail in (False, True):
            captured = {}
            def observe(connection):
                captured["connection"] = connection
                captured["path"] = Path(connection.execute("PRAGMA database_list").fetchone()[2])
                self.assertTrue(captured["path"].exists())
                if fail:
                    raise OSError("synthetic stat failure")
                return snapshot(connection)
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as directory:
                paths = profiler.write_synthetic(directory, 10, 32)
                with patch.object(profiler, "storage_snapshot", side_effect=observe):
                    if fail:
                        with self.assertRaisesRegex(OSError, "synthetic stat failure"):
                            profiler.measure(paths, "sqlite")
                    else:
                        self.assertIsNotNone(profiler.measure(paths, "sqlite")["index_storage"])
            self.assertIs(profiler.datasetlint.open_indexes, original)
            self.assertFalse(captured["path"].parent.exists())
            with self.assertRaises(sqlite3.ProgrammingError):
                captured["connection"].execute("SELECT 1")

    @unittest.skipUnless(sys.platform == "linux", "Linux profiling")
    def test_invalid_scan_skips_observation_and_cleans_storage(self):
        original = profiler.datasetlint.open_indexes
        created = []
        real_temporary = tempfile.TemporaryDirectory
        def temporary(*args, **kwargs):
            directory = real_temporary(*args, **kwargs)
            created.append(Path(directory.name))
            return directory
        with real_temporary() as directory:
            paths = profiler.write_synthetic(directory, 10, 32)
            paths["train"].write_text('{"id":"late-invalid"}\n', encoding="utf-8")
            with patch.object(profiler.indexes, "TemporaryDirectory", side_effect=temporary), \
                    patch.object(profiler, "storage_snapshot") as observe:
                with self.assertRaises(ValueError):
                    profiler.measure(paths, "sqlite")
                observe.assert_not_called()
        self.assertTrue(created)
        self.assertTrue(all(not path.exists() for path in created))
        self.assertIs(profiler.datasetlint.open_indexes, original)

    @unittest.skipUnless(sys.platform == "linux", "Linux profiling")
    def test_missing_observation_is_error_and_cli_emits_no_partial_report(self):
        with patch.object(profiler.jsonl, "inspect_jsonl", return_value={}):
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = profiler.main(["--worker", "sqlite", "train.jsonl", "test.jsonl"])
        self.assertEqual((code, out.getvalue()), (2, ""))
        self.assertIn("observation was not captured", err.getvalue())
