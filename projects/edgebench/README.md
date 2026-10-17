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

Exit codes: 0 demo completed or saved report validated, 2 invalid settings/report
or file error. No memory, energy,
throughput, model-quality or full hardware-identification claims are made.
MIT licensed. Developed with AI assistance.
