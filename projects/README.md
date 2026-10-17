# AI evaluation projects

Three standalone Python packages are staged here for development. They do not
depend on BenchGuard or on each other. The GitHub connection currently supports
editing existing repositories but exposes no action to create repositories.
Separate repository publication is pending; these directories can be moved
without changing their code. No PyPI packages have been published.

| Project | Working first version | Next milestone |
| --- | --- | --- |
| DatasetLint | JSON/JSONL duplicate checks, field mapping, file/line diagnostics and JSONL source hashes | Opt-in normalization and disk-backed indexes |
| EdgeBench | Callable timings, configuration snapshots and offline saved-report validation | Configuration compatibility and hardware runs |
| VisionEval | Saved digit/arithmetic scoring, optional outcomes and explicit whole-response numeric parsing | Reviewed format adapters and pinned-protocol exports |

2026-10-17: local standard-library suites passed: DatasetLint 25, EdgeBench 20,
VisionEval 19. Fixtures are synthetic. EdgeBench's smoke test executes a SHA-256
workload on the current host; no model inference or Raspberry Pi run was made.
See each package's README, ROADMAP and MIT LICENSE. Work developed with AI
assistance. Contributions should document the use case, tests actually run and
data licenses. Do not fabricate measurements or expose private research data.

The repository workflow runs each package's tests on Python 3.10, 3.12 and 3.13.
When extracting a package into its own repository, copy its directory contents
and add a workflow using the commands in its README.
