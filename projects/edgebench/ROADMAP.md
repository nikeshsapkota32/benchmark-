# Roadmap

- Implemented: callable timing API, warm-up exclusion, completion callback,
  raw durations, nearest-rank percentiles, host metadata and CPU demo. Optional
  structured model/runtime/input configuration is validated and snapshotted
  before measurement; the CLI demo records its actual synthetic settings.
- Implemented: offline saved-report schema and summary-consistency validation
  through the API and `--validate`; validation does not establish provenance.
- Implemented: `strict-metadata-v1` compatibility checks with required protocol,
  optional additional required fields and explicit missing/different diagnostics.
- Next: reviewed policies for experiments that intentionally vary selected settings.
- Add repeatable workload adapters with loading excluded from inference timing.
- Run on actual Raspberry Pi hardware when access exists; record temperature,
  power mode, runtime versions and repeatability before publishing comparisons.
- Add platform-aware resource measurement with explicit units and limitations.
- Consider a BenchGuard export only for compatible workload protocols.
