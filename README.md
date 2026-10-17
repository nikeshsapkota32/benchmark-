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
between zero and one means one percentage point. Use separate comparisons when
metrics need different tolerances; per-metric policy is planned.

Model identifiers may differ. Dataset revision and protocol must match exactly.
Sample counts and metric direction must match for each task/metric pair.
Missing baseline metrics fail; added metrics are reported but are not gated.
Empty runs, duplicate results, duplicate JSON keys, nonfinite scores and invalid
counts are errors. Output order is deterministic.
Scores and tolerances must fit within Python's finite floating-point range;
out-of-range JSON integers are input errors as well.

| Exit code | Meaning |
| --- | --- |
| 0 | All baseline metrics pass |
| 1 | Regression, missing metric or incompatible result |
| 2 | Malformed input, incompatible run metadata or file error |

## What this does not prove

This is a deterministic regression gate, not a statistical significance test.
Equal counts do not prove that two runs evaluated the same samples. Pin dataset
revisions and include sampling, prompt, inference and evaluator settings in the
protocol string. The tool trusts this metadata; it cannot verify its provenance.
No benchmark runner, model inference, GPU profiling or native lm-eval/LightEval
adapter is included yet. A passing report does not establish general model quality.

## Development

The core lives in `src/benchguard/core.py`; the CLI handles files and exit codes.
Tests run on the standard library alone. CI is configured for Python 3.10, 3.12
and 3.13; those remote jobs have not run until the project is published.

Contributions should include a failing example or a specific use case, a focused
change and relevant tests. Describe what actually changed in the commit message.
Do not fabricate benchmark results or create empty activity commits. Follow
upstream disclosure requirements when preparing contributions to other projects.
The initial implementation was developed with AI assistance.

See [ROADMAP.md](ROADMAP.md) for the next milestones. MIT licensed.
