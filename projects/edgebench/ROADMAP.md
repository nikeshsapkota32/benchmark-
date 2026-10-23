# Roadmap

- Implemented: callable timing API, warm-up exclusion, completion callback,
  raw durations, nearest-rank percentiles, host metadata and CPU demo. Optional
  structured model/runtime/input configuration is validated and snapshotted
  before measurement; the CLI demo records its actual synthetic settings.
- Implemented: offline saved-report schema and summary-consistency validation
  through the API and `--validate`; validation does not establish provenance.
- Implemented: saved-file JSON decoder nesting-limit failures return exit 2
  without partial validation/comparison/audit output; supported extras and
  exact-byte hashes are unchanged, with no global recursion-setting changes.
- Implemented: reject async callbacks and awaitable/async-generator return values
  instead of reporting coroutine creation as completed work. No event loop is run.
- Implemented: reject Python generator callbacks and generator return values;
  callers must explicitly consume streaming work within the timed callback.
- Implemented: `strict-metadata-v1` compatibility checks with required protocol,
  optional additional required fields and explicit missing/different diagnostics.
- Implemented: opt-in `controlled-fields-v1` policy for explicitly varied
  configuration fields; both values remain required, permitted changes are
  reported, and protocol/environment checks remain strict. Experiments still
  require human review of controlled variables and omitted metadata.
- Add repeatable workload adapters with loading excluded from inference timing.
- Implemented first example: dependency-free dense linear classifier with
  explicitly synthetic/untrained fixtures. Loading, validation, conversion and
  exact-byte model/input hashing precede warm-up and measurement; the timed
  boundary includes arithmetic, allocation, finiteness checks and argmax.
  Model-quality validation remains future work.
- Implemented optional NumPy CPU example (#51): shared strict fixture validation,
  read-only float64 arrays, distinct matvec/bias/argmax timing protocol, exact-byte
  identities and verified/restored BLAS thread limits. Native backend versions
  are recorded without library paths. Optional dependency CI is separate from
  the dependency-free core. Larger licensed workloads and actual Pi measurements
  remain future work; the tiny synthetic fixture makes no accuracy/speed claim.
- Implemented: opt-in exact-byte input hashes for saved-report CLI comparisons,
  using the same reads for parsing and hashing without claiming provenance.
- Implemented: offline descriptive latency comparisons after strict or
  controlled-fields compatibility checks, with recomputed summaries and signed
  millisecond deltas. Incompatible reports produce no numeric comparisons;
  performance gating and statistical significance remain separate future work.
- Run on actual Raspberry Pi hardware when access exists; record temperature,
  power mode, runtime versions and repeatability before publishing comparisons.
- Add platform-aware resource measurement with explicit units and limitations.
- Consider a BenchGuard export only for compatible workload protocols.
