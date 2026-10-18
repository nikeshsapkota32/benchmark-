"""Synthetic exports shaped like lm-evaluation-harness EvalResults, not real scores."""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from benchguard.core import compare
from benchguard.lm_eval_adapter import adapt, main


def fixture():
    return {
        "results": {"toy": {"name": "toy", "alias": "Toy", "sample_len": 3,
                            "acc,none": 0.75, "acc_stderr,none": 0.1}},
        "configs": {"toy": {"task": "toy", "dataset_path": "synthetic/toy",
                             "output_type": "multiple_choice"}},
        "versions": {"toy": 1},
        "n-shot": {"toy": 0},
        "higher_is_better": {"toy": {"acc": True}},
        "n-samples": {"toy": {"original": 10, "effective": 3}},
        "config": {"model": "hf", "model_args": "pretrained=synthetic/base",
                   "limit": 3, "gen_kwargs": None, "random_seed": 0,
                   "numpy_seed": 1, "torch_seed": 2, "fewshot_seed": 3},
        "git_hash": "test-harness-revision",
        "task_hashes": {"toy": "synthetic-sample-hash"},
    }


def convert(data=None, **changes):
    options = dict(task="toy", metric="acc,none", model="base@abc",
                   dataset_revision="dataset@abc", protocol="prompt=v1")
    options.update(changes)
    return adapt(fixture() if data is None else data, **options)


class LmEvalAdapterTests(unittest.TestCase):
    def test_recorded_chat_settings_changes_block_comparison(self):
        for key, before, after in (
            ("system_instruction", "Answer briefly", "Explain your answer"),
            ("system_instruction_sha", "hash-a", "hash-b"),
            ("chat_template", "template A", "template B"),
            ("chat_template_sha", "hash-a", "hash-b"),
            ("fewshot_as_multiturn", False, True),
        ):
            with self.subTest(key=key):
                baseline, candidate = fixture(), fixture()
                baseline[key], candidate[key] = before, after
                with self.assertRaisesRegex(ValueError, "incompatible protocol"):
                    compare(convert(baseline), convert(candidate))

    def test_chat_settings_preserve_null_empty_and_missing(self):
        baseline = convert()
        self.assertEqual(json.loads(baseline["protocol"])["chat_settings"], {})
        for key in ("system_instruction", "system_instruction_sha", "chat_template",
                    "chat_template_sha", "fewshot_as_multiturn"):
            with self.subTest(key=key):
                data = fixture()
                data[key] = None
                run = convert(data)
                self.assertEqual(json.loads(run["protocol"])["chat_settings"], {key: None})
                with self.assertRaisesRegex(ValueError, "incompatible protocol"):
                    compare(baseline, run)
                data[key] = False if key == "fewshot_as_multiturn" else ""
                with self.assertRaisesRegex(ValueError, "incompatible protocol"):
                    compare(run, convert(data))

    def test_identical_chat_settings_are_deterministic_and_allow_model_changes(self):
        data = fixture()
        data.update(system_instruction="Answer\nexactly: \u03c0", system_instruction_sha=None,
                    chat_template="{{ messages }}", chat_template_sha="recorded-hash",
                    fewshot_as_multiturn=False)
        baseline = convert(data)
        candidate = convert(dict(reversed(list(data.items()))), model="new@def")
        self.assertEqual(baseline["protocol"], candidate["protocol"])
        self.assertEqual(compare(baseline, candidate)[0].status, "pass")

    def test_invalid_chat_setting_types_rejected(self):
        for key in ("system_instruction", "system_instruction_sha", "chat_template",
                    "chat_template_sha", "fewshot_as_multiturn"):
            invalid = (0, 1, "false", [], {}) if key == "fewshot_as_multiturn" else (0, True, [], {})
            for value in invalid:
                with self.subTest(key=key, value=value):
                    data = fixture()
                    data[key] = value
                    with self.assertRaisesRegex(ValueError, key):
                        convert(data)

    def test_cli_invalid_chat_metadata_produces_no_partial_output(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "export.json"
            data = fixture()
            data["fewshot_as_multiturn"] = 1
            path.write_text(json.dumps(data), encoding="utf-8")
            output, error = io.StringIO(), io.StringIO()
            with redirect_stdout(output), redirect_stderr(error):
                status = main([str(path), "--task", "toy", "--metric", "acc,none",
                               "--model", "x", "--dataset-revision", "pin",
                               "--protocol", "reviewed"])
            self.assertEqual(status, 2)
            self.assertEqual(output.getvalue(), "")
            self.assertIn("fewshot_as_multiturn", error.getvalue())

    def test_converts_one_metric_and_ignores_stderr(self):
        run = convert()
        self.assertEqual(run["results"], [{"task": "toy", "metric": "acc,none",
                                           "value": 0.75, "samples": 3,
                                           "higher_is_better": True}])
        protocol = json.loads(run["protocol"])
        self.assertEqual(protocol["fewshot"], 0)
        self.assertEqual(protocol["filter"], "none")
        self.assertEqual(protocol["task_version"], 1)
        self.assertEqual(protocol["task_hash"], "synthetic-sample-hash")
        self.assertEqual(protocol["evaluation_settings"]["fewshot_seed"], 3)
        self.assertNotIn("model_args", protocol["evaluation_settings"])
        self.assertNotIn("sample_ids", run["results"][0])

    def test_model_may_change_but_score_is_compared(self):
        baseline = convert()
        candidate_export = fixture()
        candidate_export["results"]["toy"]["acc,none"] = 0.5
        candidate_export["config"]["model_args"] = "pretrained=synthetic/new"
        candidate = convert(candidate_export, model="new@def")
        self.assertEqual(compare(baseline, candidate)[0].status, "regression")

    def test_protocol_changes_block_comparison(self):
        baseline = convert()
        for path, value in (("n-shot", 1), ("versions", 2),
                            ("configs", {"task": "toy", "dataset_path": "changed"}),
                            ("config", 99)):
            with self.subTest(path=path):
                data = fixture()
                if path == "config":
                    data[path]["fewshot_seed"] = value
                else:
                    data[path]["toy"] = value
                with self.assertRaisesRegex(ValueError, "incompatible protocol"):
                    compare(baseline, convert(data))

    def test_missing_or_ambiguous_metadata_rejected(self):
        edits = (
            lambda d: d["results"]["toy"].pop("acc,none"),
            lambda d: d["results"]["toy"].update(sample_len=2),
            lambda d: d["n-samples"]["toy"].update(effective=True),
            lambda d: d["higher_is_better"]["toy"].update(acc=None),
            lambda d: d["versions"].update(toy=None),
            lambda d: d["config"].pop("fewshot_seed"),
            lambda d: d.pop("git_hash"),
            lambda d: d.update(task_hashes={"toy": 9}),
        )
        for index, edit in enumerate(edits):
            with self.subTest(index=index):
                data = fixture()
                edit(data)
                with self.assertRaises(ValueError):
                    convert(data)

    def test_rejects_group_metric_guess_and_nonfinite_score(self):
        data = fixture()
        data["groups"] = {"group": {"acc,none": 0.9}}
        with self.assertRaises(ValueError):
            convert(data, task="group")
        with self.assertRaisesRegex(ValueError, "exact metric,filter"):
            convert(data, metric="acc")
        data["results"]["toy"]["acc,none"] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite number"):
            convert(data)

    def test_cli_writes_valid_run_and_rejects_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "export.json"
            path.write_text(json.dumps(fixture()), encoding="utf-8")
            args = [str(path), "--task", "toy", "--metric", "acc,none", "--model", "x",
                    "--dataset-revision", "pinned", "--protocol", "reviewed"]
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(args), 0)
            self.assertEqual(json.loads(output.getvalue())["results"][0]["samples"], 3)
            path.write_text('{"results": {}, "results": {}}', encoding="utf-8")
            error = io.StringIO()
            with redirect_stderr(error):
                self.assertEqual(main(args), 2)
            self.assertIn("duplicate JSON key", error.getvalue())
