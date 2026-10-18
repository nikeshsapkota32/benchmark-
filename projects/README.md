# AI evaluation projects

Three standalone Python packages are staged here for development. They do not
depend on BenchGuard or on each other. The GitHub connection currently supports
editing existing repositories but exposes no action to create repositories.
Separate repository publication is pending; these directories can be moved
without changing their code. No PyPI packages have been published.

| Project | Working first version | Next milestone |
| --- | --- | --- |
| DatasetLint | JSON/JSONL duplicate checks, optional SQLite indexes, bounded findings, field mapping and source hashes | Resource characterization and reviewed format adapters |
| EdgeBench | Synchronous-call timing with async/generator-result rejection, saved-report validation and explicit controlled-variable policies | Reviewed workload adapters and hardware runs |
| VisionEval | Saved digit/arithmetic scoring, operator breakdown, numeric parsing and ground-truth-fingerprinted BenchGuard exports | Reviewed format adapters and sample-level uncertainty |

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
