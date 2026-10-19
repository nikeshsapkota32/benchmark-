# BenchGuard

Catch AI benchmark regressions before a model or evaluation change ships.

BenchGuard compares two saved JSON runs offline. It checks score direction,
sample counts and evaluation metadata before deciding whether the candidate
passes. It has no runtime dependencies and does not call model APIs.

## Quick start

Requires Python 3.10 or newer.

```sh
python -m pip install -e .
benchguard examples/baseline.json examples/candidate.json --tolerance 0.01
python -m unittest discover -s tests -v
```

The example candidate deliberately regresses, so the comparison exits with 1.
These are synthetic fixtures, not measurements from a real model.

## Input format

```json
{
  "schema_version": 1,
  "model": "my-model-revision",
  "dataset_revision": "pinned-dataset-commit",
  "protocol": "prompt-v1;zero-shot;seed=42;temperature=0",
  "results": [
    {"task": "example", "metric": "accuracy", "value": 0.8,
     "samples": 100, "higher_is_better": true}
  ]
}
```

Use `higher_is_better: false` for latency, error rate or perplexity. The tolerance
is an absolute difference in native metric units: 0.01 for an accuracy stored
between zero and one means one percentage point.

### Different tolerances for different metrics

Use `--metric-tolerances tolerances.json` when a run mixes metrics with different
units. The JSON file maps exact metric names to nonnegative, finite absolute
tolerances. For example, this allows one percentage point of accuracy loss and
five milliseconds of latency increase:

```json
{"accuracy": 0.01, "latency_ms": 5}
```

```sh
benchguard baseline.json candidate.json --metric-tolerances tolerances.json
```

Each override applies to every task with that metric name. Metrics omitted from
the file use `--tolerance` (zero by default). An explicit zero override tightens
a more permissive default. The metric direction still comes from the run data.
Name latency metrics with their unit, and only reuse a metric name across tasks
when the unit and scale agree.

An unknown baseline metric, duplicate JSON key, negative/nonfinite tolerance,
or malformed policy exits with code 2. A metric present only in the candidate
cannot have an override. Tolerances never bypass missing results, changed sample
counts, or incompatible metadata. The report includes the effective tolerance
in the reason for each compared result.

Model identifiers may differ. Dataset revision and protocol must match exactly.
Sample counts and metric direction must match for each task/metric pair.
Missing baseline metrics fail; added metrics are reported but are not gated.
Empty runs, duplicate results, duplicate JSON keys, nonfinite scores and invalid
counts are errors. Output order is deterministic.
Scores and tolerances must fit within Python's finite floating-point range;
out-of-range JSON integers are input errors as well.
Finite scores remain comparable even when their difference exceeds that range;
the comparison preserves the tolerance boundary instead of overflowing.

Run and policy files that exceed Python's JSON decoder nesting limit are input
errors (exit 2), with no traceback or partial JSON/Markdown report. The `load()`
helper raises `ValueError` for this condition. Supported nested extra run fields
remain ignored by comparison; audit hashes still identify the exact file bytes.
The limit is interpreter-dependent: BenchGuard does not change recursion settings
or promise a fixed depth or memory bound.

### Pin metric directions independently

Two runs can agree on an incorrect `higher_is_better` value. To catch that,
provide a reviewed JSON policy separate from the run files:

```json
{"accuracy": true, "latency_ms": false}
```

```sh
benchguard baseline.json candidate.json --metric-directions directions.json
```

The Python API accepts `compare(baseline, candidate, metric_directions=policy)`.
Values must be JSON booleans: true requires higher-is-better, false requires
lower-is-better. Keys are exact baseline metric names. Each rule applies across
all tasks in both runs, including candidate-only tasks using that metric.
Conflicting run metadata is an input error (exit 2), not silently corrected.
This catches shared mistakes even when both run files contain the same direction.

Partial or empty policies are allowed; unlisted metrics retain the existing
run-metadata rules. Unknown baseline metrics, candidate-only metric names,
nonboolean values, duplicate JSON keys and non-object policy files are errors.
Tolerance overrides cannot bypass direction conflicts. Missing results, sample
identity, counts, dataset revision and protocol checks remain in force.

Default JSON output is unchanged. Markdown reports include the exact-byte
direction-policy SHA-256 in the input audit table. The policy must itself be
reviewed and versioned: BenchGuard cannot infer the scientifically correct
direction from a metric name or verify that a supplied policy is trustworthy.

### Check that runs evaluated the same samples

Optionally add `sample_ids` to each task/metric result. Provide stable string IDs
from the pinned dataset revision, with one unique ID for each evaluated sample:

```json
{"task": "example", "metric": "accuracy", "value": 0.8,
 "samples": 2, "higher_is_better": true, "sample_ids": ["test/17", "test/42"]}
```

BenchGuard compares the ID sets independently of evaluation order. Two results
with equal counts but different IDs are incompatible, as are results where only
one side supplies IDs. Each list must contain unique, nonempty strings and its
length must equal `samples`. Missing or repeated IDs cannot silently pass.

The JSON report adds `baseline_sample_fingerprint` and
`candidate_sample_fingerprint`: SHA-256 hashes of the sorted ID lists serialized
as compact ASCII-escaped JSON. The output does not include raw IDs. These hashes
are identity checks, not encryption or proof of data integrity; avoid sensitive
IDs in shared inputs. Strings are used exactly as supplied without trimming or
Unicode normalization. Use the same ID namespace and encoding across runs.

When both results omit IDs, the existing comparison behavior is preserved and
both fingerprints are null. IDs do not bypass protocol, revision or score checks.

| Exit code | Meaning |
| --- | --- |
| 0 | All baseline metrics pass |
| 1 | Regression, missing metric or incompatible result |
| 2 | Malformed input, incompatible run metadata or file error |

## Markdown review reports

```sh
benchguard examples/baseline.json examples/candidate.json --format markdown --tolerance 0.01
```

`--format markdown` prints a review-friendly report to standard output, with
the overall outcome, run metadata, metric values/statuses/reasons and an input
audit table. JSON remains the default; its report shape is unchanged. Both
formats use the same comparison rules and exit codes, so a Markdown report can
still accompany a failing CI step. Invalid inputs return exit 2 without printing
a partial report.

The audit table contains SHA-256 hashes of the exact baseline and candidate file
bytes, plus metric-tolerance and metric-direction files when supplied. Each file is read once for
both parsing and hashing. Formatting or newline changes therefore change its
hash even if parsed data is equivalent. The report also records the global
tolerance; effective per-metric limits appear in comparable rows' reasons.
Hashes identify inputs but cannot verify their provenance or model quality.

Input text is escaped inside table cells so Markdown/HTML, pipes and newlines
cannot introduce extra report structure. Reports are deterministic for the same
inputs and options and include no timestamps or input paths. They do include
model names, dataset/protocol metadata and scores, so review them before sharing.
Raw sample IDs are not included. When redirecting output to a file, choose a new
report path distinct from all inputs: shell redirection can truncate a file
before BenchGuard starts.

## Machine-readable audit reports

For CI artifact storage or downstream report processing, opt in to a versioned
JSON envelope with the same input audit information:

```sh
benchguard baseline.json candidate.json --format json-audit \
  --metric-tolerances tolerances.json --metric-directions directions.json
```

Default `--format json` still returns only `passed` and `results`; existing
consumers do not need to change. `json-audit` retains those same fields and adds:

| Field | Content |
| --- | --- |
| `schema_version` | Integer `1`, versioning this report format, not the input run schema |
| `report_type` | `"benchguard-comparison"` |
| `runs` | `baseline` and `candidate`, each containing `model`, `dataset_revision` and `protocol` |
| `policy` | Global `tolerance`, parsed `metric_tolerances` and parsed `metric_directions` |
| `source_sha256` | Exact-byte hashes for `baseline`, `candidate` and any supplied `metric_tolerances` / `metric_directions` files |

Policy maps are empty objects when no policy is supplied. An explicitly supplied
empty policy also produces an empty map, but has a source hash, distinguishing
it from an absent file. Each file is read once for parsing and hashing. Hashes
include whitespace and line endings; the normalized policy maps describe what
was applied, while hashes identify the original bytes. Result reasons retain
the effective tolerance for each comparable metric.

The format uses the same comparison and exit codes as JSON and Markdown: 0 for
pass, 1 for a failed comparison, and 2 for an input error. Input errors emit no
partial audit. Reports contain no timestamps, input paths or extra input fields.
Sample identity is represented by the existing fingerprints in `results`, not
raw `sample_ids` arrays. Output is deterministic for identical inputs/options.

Run metadata and task/metric names are caller-supplied and are preserved as JSON
strings, not sanitized for HTML or Markdown. Escape them when rendering in a
different format, and review metadata before sharing. Hashes are neither
encryption nor proof of provenance, correct measurements or model quality.
Keep the original run/policy files for reproducibility; this report is not a
replacement for them. When redirecting output, use a path distinct from inputs.

## Import an lm-evaluation-harness aggregate result

`benchguard-lmeval` converts **one explicitly selected task and filtered metric**
from a saved lm-evaluation-harness aggregate JSON export. It never runs a model.
For example, with two existing harness result files:

```sh
benchguard-lmeval baseline-results.json --task my_task --metric acc,none \
  --model baseline@commit --dataset-revision dataset@commit \
  --protocol 'prompt=v1;chat-template=none' > baseline-benchguard.json
benchguard-lmeval candidate-results.json --task my_task --metric acc,none \
  --model candidate@commit --dataset-revision dataset@commit \
  --protocol 'prompt=v1;chat-template=none' > candidate-benchguard.json
benchguard baseline-benchguard.json candidate-benchguard.json
```

The model label, pinned dataset revision and reviewed extra protocol are
required inputs, not inferred from filenames or a possibly random harness
`model_name`. Use the exact key from `results[task]`, including its filter suffix
such as `acc,none`; groups and stderr metrics are not selected automatically.
The converter uses the harness's `higher_is_better`, `n-samples.effective`,
`sample_len`, task version, `n-shot`, task config and recorded evaluation seeds
and settings. It also carries the recorded harness `git_hash`, original sample
count and optional `task_hashes[task]` into a deterministic protocol string.
Changes to any of those fields make the two converted runs incompatible.
When recorded, `system_instruction`, `system_instruction_sha`, `chat_template`,
`chat_template_sha` and `fewshot_as_multiturn` are preserved too. Changing or
removing one of these fields blocks comparison, even if the caller's protocol
label is unchanged. Missing fields remain distinct from explicit `null`; text
fields accept strings or null, and multi-turn accepts only booleans or null.
Recorded hashes are preserved, not verified against the associated text.
The protocol uses adapter version `benchguard-lmeval-v2`; regenerate both run
files if upgrading from an earlier adapter version.
See the upstream [EvalResults schema](https://github.com/EleutherAI/lm-evaluation-harness/blob/main/lm_eval/result_schema.py)
and [aggregate writer](https://github.com/EleutherAI/lm-evaluation-harness/blob/main/lm_eval/loggers/evaluation_tracker.py)
for the source format. This adapter targets that aggregate format, not the
separate per-sample JSONL export or legacy minimal result objects.

Ambiguous or missing counts, direction, version, evaluation settings, task
config or harness revision cause exit code 2. Review the inputs and protocol
before sharing; the output embeds task configuration and may contain local
paths or sensitive metadata. The recorded revision/hash is metadata, not proof
of provenance. Without per-sample IDs or a task hash, equal sample counts do
not establish equal sample identity. `--protocol` must explicitly account for
settings not captured in the saved aggregate, including an unrecorded chat
template and model invocation details that affect comparability. Absent prompt
settings do not establish that no template or system instruction was used.
Example names above are
illustrative, not measured benchmark claims.

## What this does not prove

This is a deterministic regression gate, not a statistical significance test.
Equal counts alone do not prove that two runs evaluated the same samples. Optional
sample IDs check the reported sample set, but cannot prove that those IDs refer
to unchanged content or that the reported samples were actually evaluated. Pin
dataset revisions and include sampling, prompt, inference and evaluator settings
in the protocol string. The tool trusts this metadata; it cannot verify its provenance.
No benchmark runner, model inference, GPU profiling or LightEval adapter is
included. The lm-evaluation-harness adapter imports aggregate results only;
it cannot validate the underlying evaluation. A passing report does not
establish general model quality.

## Development

The core lives in `src/benchguard/core.py`; the CLI handles files and exit codes.
Tests run on the standard library alone. CI is configured for Python 3.10, 3.12
and 3.13.

Contributions should include a failing example or a specific use case, a focused
change and relevant tests. Describe what actually changed in the commit message.
Do not fabricate benchmark results or create empty activity commits. Follow
upstream disclosure requirements when preparing contributions to other projects.
The initial implementation was developed with AI assistance.

See [ROADMAP.md](ROADMAP.md) for the next milestones. MIT licensed.
