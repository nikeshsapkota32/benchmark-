"""Original synthetic fixtures for digits-csv-v1; covered by the project MIT license."""

from contextlib import redirect_stderr, redirect_stdout
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from visioneval import evaluate
from visioneval.__main__ import main
from visioneval.csv_input import load_digits_csv
from visioneval.export import to_benchguard


META = {"model": "synthetic", "dataset_revision": "fixture-v1", "protocol": "test-only"}
HEADER = "id,target,prediction\n"


def envelope(records):
    return {"schema_version": 1, "kind": "digits", **META, "records": records}


class CsvInputTests(unittest.TestCase):
    def invoke(self, payload, *options, metadata=True, input_format="digits-csv-v1"):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "predictions.csv"
            with open(path, "wb") as stream:
                stream.write(payload if isinstance(payload, bytes) else payload.encode("utf-8"))
            argv = [str(path), "--input-format", input_format]
            if metadata:
                for key, value in META.items():
                    argv.extend(["--" + key.replace("_", "-"), value])
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                try:
                    code = main([*argv, *options])
                except SystemExit as exc:
                    code = exc.code
        return code, out.getvalue(), err.getvalue()

    def assert_invalid(self, payload, *options):
        for output_format in ("json", "benchguard"):
            code, output, error = self.invoke(payload, "--format", output_format, *options)
            self.assertEqual((code, output), (2, ""))
            self.assertTrue(error)
            self.assertNotIn("private-fixture-marker", error)
            self.assertNotIn("Traceback", error)

    def test_scores_details_and_exports_equal_explicit_json_records(self):
        records = [{"id": "a", "target": "001", "prediction": "001"},
                   {"id": "b", "target": "07", "prediction": "7"},
                   {"id": "c", "target": "5", "prediction": ""}]
        payload = HEADER + "a,001,001\nb,07,7\nc,5,\n"
        for policy in ("strict", "numeric-text-v1", "numeric-text-count-v1"):
            for output_format in ("json", "benchguard"):
                with self.subTest(policy=policy, output=output_format):
                    options = ["--format", output_format, "--response-policy", policy]
                    if output_format == "json":
                        options.append("--details")
                        expected = evaluate(envelope(records), response_policy=policy, include_details=True)
                    else:
                        expected = to_benchguard(envelope(records), response_policy=policy)
                    code, output, error = self.invoke(payload, *options)
                    self.assertEqual((code, error), (0, ""))
                    self.assertEqual(json.loads(output), expected)
        report = json.loads(self.invoke(payload)[1])
        self.assertEqual((report["samples"], report["correct"], report["missing"],
                          report["digit_edit_errors"], report["target_digits"]), (3, 1, 1, 2, 6))

    def test_quoting_unicode_bom_and_embedded_newlines_preserve_strings(self):
        records = [{"id": ' Δ,"a"\r\nb ', "target": "001", "prediction": " 001\r\n"}]
        for ending in ("\n", "\r\n"):
            stream = io.StringIO(newline="")
            writer = csv.writer(stream, lineterminator=ending)
            writer.writerow(["id", "target", "prediction"])
            writer.writerow(list(records[0].values()))
            for prefix in ("", "\ufeff"):
                payload = prefix + stream.getvalue()
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "input.csv"
                    path.write_bytes(payload.encode("utf-8"))
                    self.assertEqual(load_digits_csv(path, **META), envelope(records))
                code, output, error = self.invoke(payload, "--response-policy", "numeric-text-v1",
                                                 "--format", "benchguard")
                self.assertEqual((code, error), (0, ""))
                self.assertEqual(json.loads(output), to_benchguard(envelope(records),
                                                                response_policy="numeric-text-v1"))

    def test_empty_and_textual_nulls_follow_existing_response_policies(self):
        payload = HEADER + 'a,1,\nb,2,""\nc,3,null\nd,4,NaN\ne,5,N/A\n'
        self.assert_invalid(payload)
        self.assert_invalid(payload, "--response-policy", "numeric-text-v1")
        code, output, error = self.invoke(payload, "--response-policy", "numeric-text-count-v1")
        self.assertEqual((code, error), (0, ""))
        report = json.loads(output)
        self.assertEqual((report["samples"], report["missing"], report["unparseable"],
                          report["digit_edit_errors"]), (5, 2, 3, 5))

    def test_headers_must_be_exact_and_data_must_be_present(self):
        for header in ("", "id,target", "id,target,target", "target,id,prediction",
                       "id,target,prediction,extra", "id;target;prediction",
                       " id,target,prediction"):
            with self.subTest(header=header):
                self.assert_invalid(header + "\nprivate-fixture-marker,1,1\n")
        for payload in ("", HEADER, HEADER.rstrip("\n")):
            self.assert_invalid(payload)

    def test_later_bad_rows_are_not_dropped_or_partially_reported(self):
        for row in ("\n", "b,2\n", "b,2,2,extra\n", 'b,2,"unterminated',
                    'b,2,"2"extra\n', "a,2,2\n", "b,१२,1\n", "b,,1\n"):
            with self.subTest(row=row):
                self.assert_invalid(HEADER + "a,1,1\n" + row,
                                    "--response-policy", "numeric-text-count-v1")

    def test_no_target_trimming_or_missing_id_inference(self):
        for row in ("a, 01,01\n", "a,01 ,01\n", ",1,1\n", "   ,1,1\n"):
            self.assert_invalid(HEADER + row)
        code, output, error = self.invoke(HEADER + "a,01, 01\n", "--response-policy", "numeric-text-v1")
        self.assertEqual((code, error), (0, ""))
        self.assertEqual(json.loads(output)["correct"], 1)

    def test_metadata_is_required_and_cannot_override_json(self):
        for missing in META:
            options = []
            for key, value in META.items():
                if key != missing:
                    options.extend(["--" + key.replace("_", "-"), value])
            code, output, error = self.invoke(HEADER + "a,1,1\n", *options, metadata=False)
            self.assertEqual((code, output), (2, ""))
            self.assertIn("CSV input requires", error)
        for key in META:
            self.assert_invalid(HEADER + "a,1,1\n", "--" + key.replace("_", "-"), " ")
        item = envelope([{"id": "a", "target": "01", "prediction": "01"}])
        code, output, error = self.invoke(json.dumps(item), input_format="json", metadata=False)
        self.assertEqual((code, error), (0, ""))
        self.assertEqual(json.loads(output), evaluate(item))
        code, output, error = self.invoke(json.dumps(item), input_format="json")
        self.assertEqual((code, output), (2, ""))
        self.assertIn("require --input-format digits-csv-v1", error)

    def test_parser_limits_remain_unchanged_and_files_close_on_error(self):
        original = csv.field_size_limit()
        try:
            csv.field_size_limit(32)
            self.assert_invalid(HEADER + "a,1," + "1" * 33 + "\n")
            self.assertEqual(csv.field_size_limit(), 32)
        finally:
            csv.field_size_limit(original)
        for payload in (HEADER + 'a,1,"unterminated', HEADER + "a,1\n", HEADER + "a,1,1\n"):
            stream = io.StringIO(payload)
            with patch("visioneval.csv_input.Path.open", return_value=stream):
                try:
                    load_digits_csv("unused.csv", **META)
                except ValueError:
                    pass
            self.assertTrue(stream.closed)
        class ReadFailure(io.StringIO):
            def __next__(self):
                if self.tell():
                    raise OSError("synthetic read failure")
                return super().__next__()

        stream = ReadFailure(HEADER + "a,1,1\n")
        with patch("visioneval.csv_input.Path.open", return_value=stream):
            with self.assertRaisesRegex(OSError, "synthetic read failure"):
                load_digits_csv("unused.csv", **META)
        self.assertTrue(stream.closed)

    def test_invalid_utf8_and_read_failures_produce_no_output(self):
        self.assert_invalid(HEADER.encode() + b"a,1,\xff\n")
        with patch("visioneval.csv_input.Path.open", side_effect=OSError("synthetic read failure")):
            self.assert_invalid(HEADER + "a,1,1\n")

    def test_csv_mode_rejects_arithmetic_only_options(self):
        self.assert_invalid(HEADER + "a,1,1\n", "--by-operator")
