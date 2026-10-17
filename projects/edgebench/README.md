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

`benchmark(operation, workload=..., warmups=3, repeats=10, synchronize=None)`
discards warm-up calls, then measures each call with `perf_counter_ns`. An
optional synchronization callback completes pending device work before the run
and after every operation, inside the timed region. Without it, operations must
finish synchronously. Exceptions abort the run instead of reporting partial
success. The callable's outputs are discarded; validate correctness separately.

The JSON report includes every measured duration in milliseconds, min/max,
mean, median, p90/p95, warm-up/repeat counts, OS/release, machine architecture and
Python version. Percentiles use nearest rank (`ceil(p*n)`); small samples give
coarse estimates. Device queues, thermal throttling, background load, thread
counts and power settings affect timings. Record those in the workload
description until structured metadata is available. Report metadata may reveal
host OS information; review before sharing.

Exit codes: 0 demo completed, 2 invalid CLI settings. No memory, energy,
throughput, model-quality or full hardware-identification claims are made.
MIT licensed. Developed with AI assistance.
