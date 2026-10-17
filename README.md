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

## What this does not prove

This is a deterministic regression gate, not a statistical significance test.
Equal counts alone do not prove that two runs evaluated the same samples. Optional
sample IDs check the reported sample set, but cannot prove that those IDs refer
to unchanged content or that the reported samples were actually evaluated. Pin
dataset revisions and include sampling, prompt, inference and evaluator settings
in the protocol string. The tool trusts this metadata; it cannot verify its provenance.
No benchmark runner, model inference, GPU profiling or native lm-eval/LightEval
adapter is included yet. A passing report does not establish general model quality.

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
