# EdgeBench

Measure a Python callable's completed-call latency on the current machine.
Python 3.10+, standard-library only. Intended for CPU and Raspberry Pi inference
experiments; this initial version provides the timing API and a synthetic demo.

```sh
python -m pip install -e .
edgebench --demo --warmups 3 --repeats 10
PYTHONPATH=src python -m unittest discover -s tests -v
```

The demo hashes one MiB with SHA-256. Its output describes the actual host and
labels the workload as synthetic. It does not load a model or claim Raspberry
Pi performance. Use the API to measure your own inference callable:

```python
from edgebench import benchmark

# Load your model and fixed inputs before measuring.
# report = benchmark(lambda: model(fixed_input), workload="model/revision;input-shape;runtime")
```

`benchmark(operation, workload=..., warmups=3, repeats=10, synchronize=None,
configuration=None)`
discards warm-up calls, then measures each call with `perf_counter_ns`. An
optional synchronization callback completes pending device work before the run
and after every operation, inside the timed region. Without it, operations must
finish synchronously. Exceptions abort the run instead of reporting partial
success. The callable's outputs are discarded; validate correctness separately.

Both callbacks must be synchronous Python callables. Coroutine functions and
async-generator functions (including detectable partials, methods and async
`__call__` objects) are rejected before any operation or synchronization runs.
Return values are also checked after every call: a synchronous wrapper returning
an awaitable or async generator raises `ValueError`, even during warm-up or the
initial synchronization. No timing report is returned after such a failure.
This prevents coroutine creation from being reported as completed inference.

EdgeBench does not run an event loop or await results. Native coroutine results
are closed to avoid unawaited-coroutine warnings; other awaitables/tasks are not
awaited or cancelled. The caller remains responsible for outstanding work and
cleanup. A late failure cannot undo earlier calls or their side effects. If a
workload uses asynchronous device execution, provide a **synchronous blocking**
completion callback; returning an awaitable from that callback is not sufficient.
Ordinary return values are still discarded. These checks cannot detect every
lazy result or hidden device queue, so completion remains the caller's contract.

Python generator functions are also rejected before any work runs. Calling one
creates a generator without executing its body, so timing that call would not
measure completed work. Wrappers returning a generator (including a generator
expression or an already started generator) are rejected after the call, during
any phase of measurement or synchronization. EdgeBench neither consumes nor
closes these caller-owned generators; the caller is responsible for cleanup.
To benchmark a streaming operation, consume it explicitly inside the callback,
for example `benchmark(lambda: list(generate()), workload="full stream")`.
That example includes consumption and list allocation in the timing; choose and
document the consumption strategy that matches your workload.

Per-call dispatch and return-value checks are inside the measured interval,
along with the synchronization callback. Their overhead can matter for very
short operations; this is completed-call latency under the harness, not a
measurement of a device kernel in isolation. Keep harness versions and timing
boundaries consistent when comparing results.

The JSON report includes every measured duration in milliseconds, min/max,
mean, median, p90/p95, warm-up/repeat counts, OS/release, machine architecture and
Python version. Percentiles use nearest rank (`ceil(p*n)`); small samples give
coarse estimates. Device queues, thermal throttling, background load, thread
counts and power settings affect timings. Report metadata may reveal host OS
information; review before sharing.

## Record the workload configuration

Pass a `configuration` dictionary to the API to attach structured settings:

```python
configuration = {
    "model": "example-model", "model_revision": "pinned-weights-revision",
    "runtime": "example-runtime", "runtime_version": "1.0",
    "device": "cpu", "dtype": "float32", "input_shape": [1, 3, 28, 28],
    "input_revision": "fixed-input-revision", "batch_size": 1, "threads": 2,
    "protocol": "inference only; preprocessing excluded; fixed power mode",
}
# Supply your loaded model and fixed input:
# report = benchmark(lambda: model(fixed_input), workload="digit inference",
#                    configuration=configuration)
```

All fields are optional; omitted configuration is reported as `{}`. Supported
string fields are `model`, `model_revision`, `runtime`, `runtime_version`,
`device`, `dtype`, `input_revision` and `protocol`, each nonblank. `batch_size`
and `threads` must be positive integers. `input_shape` must be a nonempty list
of positive integer dimensions. Booleans, unknown fields and invalid values
are rejected before the operation or synchronization callback runs.

Settings are copied before warm-up and reported under `configuration`. Changing
the original dictionary or shape list during execution does not alter that
snapshot. The independently collected `environment` fields still describe the
host. Configuration is caller-reported: EdgeBench does not apply thread counts,
verify model revisions, inspect tensor shapes, or check that settings match the
operation. Omitted fields mean unspecified, not defaults. Record device queues,
preprocessing boundaries, power mode and other relevant settings in `protocol`.

The CLI demo fills in Python/hashlib, the Python version, CPU, byte input and its
1 MiB shape automatically. It has no model field because it performs no inference.

## Validate a saved report

```sh
edgebench --demo --warmups 3 --repeats 10 > timing.json
edgebench --validate timing.json
```

Validation is offline and does not execute the workload. The Python API
`from edgebench import validate_report` accepts a parsed report dictionary,
returns `None` on success and raises `ValueError` on invalid data without
changing the input. The CLI prints only
`{"valid": true, "schema_version": 1, "repeats": 10}` on success; it does not
copy workload or host metadata into that acknowledgement. Errors go to stderr
with no partial stdout report. `--validate` cannot be combined with `--demo`,
`--warmups` or `--repeats`.

Checks include integer schema version 1, nonblank workload, integer warm-up and
repeat counts, `ms` units, nearest-rank percentiles, environment string fields,
and configuration types. Early schema-v1 reports without `configuration` remain
valid; an explicit null configuration is invalid. Environment values may be empty
strings when host information was unavailable. Unknown report/environment/summary
fields are ignored; configuration fields retain their documented strict allowlist.

Raw timings must be finite, nonnegative numbers (not booleans), with exactly one
entry per repeat. Zero timings are allowed because clock resolution may be too
coarse for short operations. Each summary is recomputed from these durations.
Min/max and nearest-rank percentiles must match exactly. Mean and median allow
relative error up to `1e-12` with no absolute tolerance for serialization rounding;
aggressively rounded reports may fail. Even-sample medians avoid overflowing the
sum of two large finite values. Duplicate JSON keys, NaN/Infinity constants,
malformed UTF-8/JSON and missing files are errors. Reports are loaded into memory.

Passing validates internal consistency, not authenticity, hardware identity,
statistical reliability, configuration compatibility or model correctness. A
fabricated but self-consistent report can pass. Keep original measurements and
protocol records; this command cannot prove that any benchmark actually ran.

## Check whether measurement settings match

```sh
edgebench --check-compatible baseline.json candidate.json --require-field model_revision --require-field input_revision
```

The Python API is `check_compatibility(baseline, candidate, required_fields=())`,
imported from `edgebench`. Both reports must first pass saved-report validation.
The versioned `strict-metadata-v1` policy requires exact matches for workload,
warm-up/repeat counts, OS/release, architecture and Python version. Empty or
whitespace-only environment strings count as missing information.

Configuration `protocol` is always required in both reports. Repeat
`--require-field NAME` to require additional supported configuration fields;
the API accepts a list or tuple. Unknown names are errors. Every configuration
field present in either report must be present and equal in the other, whether
explicitly required or not. Fields omitted by both reports are unspecified;
require the fields relevant to your experiment. Legacy reports without
configuration therefore validate individually but fail this compatibility check.

The JSON result contains `compatible`, the policy name, sorted `required_fields`
and a deterministic `differences` list. Each difference names its field and gives
`different`, `missing_in_baseline`, `missing_in_candidate` or `missing_in_both`.
It does not copy the recorded values. Durations may differ: this checks metadata,
not performance regressions or statistical significance. Unknown extension fields
outside configuration are ignored, consistent with schema-v1 validation.

Exit 0 means these metadata checks passed, 1 means incompatible metadata, and 2
means malformed input, invalid options or a file error. No workload executes.
Malformed reports produce no partial result. Matching metadata does not establish
identical physical hardware, power/thermal conditions, accurate caller settings,
or a fair experiment. This strict policy intentionally flags changes to model,
runtime or hardware settings; comparisons that intentionally vary them need a
separately specified experimental policy.

## Declare intentionally varied configuration settings

To compare an experiment that intentionally changes thread count, for example:

```sh
edgebench --check-compatible baseline.json candidate.json --vary-field threads \
  --require-field model_revision --require-field input_revision
```

The Python API accepts `vary_fields=["threads"]`. A nonempty list/tuple selects
the explicit `controlled-fields-v1` policy. Repeat `--vary-field NAME` for multiple
settings. Supported names are the configuration fields listed above **except
`protocol`**. Nested paths, environment fields and unknown names are errors.
Omitting the option, or supplying an empty API list/tuple, preserves the strict
policy and its existing report shape.

Declared fields must be present and valid in **both** reports; they are included
in `required_fields` automatically. Only their equality check is relaxed. Missing
values, including fields absent from both reports, remain incompatibilities.
Declaring a field does not require it to change: unchanged values are accepted.
You may also list the same field in `required_fields`; presence is still required
but an explicitly permitted value change is allowed.

The result adds sorted `vary_fields` and a `permitted_differences` list using the
same field/reason shape as `differences`, without copying raw values. Declared
value changes go in `permitted_differences`; missing fields and all other changes
stay in `differences` and fail compatibility. Duplicate declarations are collapsed.
The workload, warm-up/repeat counts, host environment and configuration protocol
must still match. Both reports undergo full saved-report validation first.

This is an allowlist of experimental variables, **not** an automatic fair-comparison
policy, performance gate or significance test. Pin and require all relevant fixed
settings, review the declared variables, and retain original reports to inspect
their values. Multiple variables may confound attribution; the tool does not infer
causality. It cannot verify that caller-reported settings were actually applied.
Exit codes remain 0 for policy-compatible metadata, 1 for incompatible metadata,
and 2 for invalid inputs/options. No workload executes in this mode.

## Compare saved latency summaries

```sh
edgebench --compare baseline.json candidate.json \
  --require-field model_revision --require-field input_revision
# For a reviewed thread-count experiment, also add: --vary-field threads
```

The API `compare_reports(baseline, candidate, required_fields=(), vary_fields=())`,
imported from `edgebench`, validates both saved reports and applies the same
strict or controlled-fields compatibility policy described above. It never
executes the workload. `--check-compatible` retains its existing output shape.

The new comparison envelope contains `schema_version: 1`,
`report_type: "edgebench-comparison"`, `unit: "ms"`, the complete policy result
under `compatibility`, and a `metrics` list. For compatible reports, that list
contains `min`, `max`, `mean`, `median`, `p90` and `p95` in that order. Each row
includes `baseline`, `candidate` and `delta_ms` (candidate minus baseline).
Positive deltas mean increased latency; negative deltas mean reduced latency.
Values are recomputed from raw durations rather than the saved, possibly rounded
summaries. Zero timings are supported; no ratios or percentages are calculated.

For incompatible metadata, `metrics` is empty and the compatibility diagnostics
explain why no timing comparison was made. Malformed inputs produce exit 2 and
no partial stdout report. Exit 1 means incompatible metadata. Exit 0 means a
comparison was produced, **even when every latency increased**: there is no
performance threshold, pass/fail judgment, statistical test or causal claim.
Small repeat counts and noisy measurements still limit interpretation.

Results do not copy raw durations or workload, configuration and environment
values. Timing summaries themselves may be sensitive; review before sharing.
Keep the original reports and experimental protocol. Matching metadata cannot
verify physical hardware identity or prove a fair or reproducible experiment.
`--require-field` and `--vary-field` work in both comparison modes; `--warmups`
and `--repeats` remain demo-only. Output is deterministic for identical inputs.

Exit codes for other modes: 0 demo completed or saved report validated, 2 invalid settings/report
or file error. No memory, energy,
throughput, model-quality or full hardware-identification claims are made.
MIT licensed. Developed with AI assistance.
