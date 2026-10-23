# AI evaluation projects

Three separately installable Python packages are staged here. They do not depend
on BenchGuard or on each other. The portfolio pull request remains a draft while
the final repository layout is decided. No PyPI packages have been published.

| Project | Working first version | Next milestone |
| --- | --- | --- |
| DatasetLint | JSON/JSONL duplicate and overlap checks, optional finding summaries and SQLite indexes, field mapping and source hashes | Broader resource characterization and reviewed format adapters |
| EdgeBench | Completed-call timing, saved-report checks, controlled-variable policies and synthetic linear/optional NumPy CPU examples | Reviewed workloads and measurements on actual hardware |
| VisionEval | Digit/arithmetic scoring, digit CSV import, numeric response policies and ground-truth-fingerprinted BenchGuard exports | Reviewed arithmetic/model-export adapters and sample-level uncertainty |

Fixtures are synthetic; tests are not model-quality or hardware benchmark results.
See each package's README, ROADMAP and MIT LICENSE. Work developed with AI
assistance. Contributions should document the use case, tests actually run and
data licenses. Do not fabricate measurements or expose private research data.

The repository workflow runs each package's tests on Python 3.10, 3.12 and 3.13.
When extracting a package into its own repository, copy its directory contents
and add a workflow using the commands in its README.

## Cross-package CLI contract tests

From the repository root:

```sh
python -m pip install -e . -e projects/visioneval
python -m unittest discover -s integration_tests -v
```

The integration CI job runs these commands on Python 3.10, 3.12 and 3.13.
It exports synthetic predictions through the VisionEval CLI and passes the saved
runs to the BenchGuard CLI, checking exit codes, source hashes, metric directions,
missing predictions and incompatible ground truth or response policies. Invalid
exports must fail without partial output. No inference or network access is
required by the tests. These tests live outside each package's standalone suite;
neither package gains a runtime dependency on the other. Keep this integration
job (or an equivalent version-pinned compatibility job) when splitting repositories.

## Installed-wheel checks

The `Installed wheel tests` workflow builds all four packages and installs only
those wheels into a fresh virtual environment on Python 3.10, 3.12 and 3.13.
It verifies imports come from that environment's `site-packages`, checks all four
console scripts with `--help`, and reruns the unit and integration suites from
an empty temporary working directory. Isolated Python mode and a cleaned child
environment prevent `PYTHONPATH` or the current directory from supplying source
packages. Editable-install CI remains in place as a separate development check.
Four harness regression tests also check its isolation, environment, source-import
and console-entry-point guards (`python -m unittest discover -s scripts -v`).

To reproduce on Linux/macOS from the repository root:

```sh
check_dir=$(mktemp -d)
python -m pip wheel --no-deps --wheel-dir "$check_dir/wheels" \
  . ./projects/datasetlint ./projects/edgebench ./projects/visioneval
python -m venv "$check_dir/venv"
"$check_dir/venv/bin/python" -m pip install --no-index --no-deps \
  --find-links "$check_dir/wheels" benchguard datasetlint edgebench visioneval
"$check_dir/venv/bin/python" -I scripts/check_installed.py
```

Building may download build dependencies; installation and checks use only the
built wheels and local synthetic fixtures. For an offline build with suitable
build dependencies already installed, add `--no-build-isolation --no-index` to
the wheel command. The check requires a fresh virtual environment and `-I` and
fails if a package, entry point, CLI or test suite fails. Tests/fixtures remain
in the checkout; only application imports must come from installed packages.
This checks installability, not PyPI publication, reproducible wheel bytes,
model quality or hardware performance. No artifacts are published by the job.
