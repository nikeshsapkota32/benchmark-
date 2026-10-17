# Roadmap

- Implemented: callable timing API, warm-up exclusion, completion callback,
  raw durations, nearest-rank percentiles, host metadata and CPU demo.
- Next: structured model/runtime/input metadata and raw-report schema checks.
- Add repeatable workload adapters with loading excluded from inference timing.
- Run on actual Raspberry Pi hardware when access exists; record temperature,
  power mode, runtime versions and repeatability before publishing comparisons.
- Add platform-aware resource measurement with explicit units and limitations.
- Consider a BenchGuard export only for compatible workload protocols.
