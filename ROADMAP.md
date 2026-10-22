# Development plan

## Next: real evaluation artifacts
- lm-evaluation-harness aggregate adapter: implemented for one explicitly
  selected task/filtered metric; preserves task version, few-shot, filter,
  counts, task config, settings and optional task hash, using synthetic tests.
- Recorded chat/system-instruction fields now participate in compatibility,
  including missing-versus-null distinctions. Schema/writer inspected at
  [harness d6de816](https://github.com/EleutherAI/lm-evaluation-harness/blob/d6de81643928d653435c431bae19945d41d32520/lm_eval/result_schema.py)
  on 2026-10-18. Synthetic regressions reproduce the previously ignored template
  change; this is not yet validation against a real model export.
- Next: validate with a suitably licensed real export and consider a
  per-sample JSONL option for sample identity; do not infer IDs from counts.
- Main's decoder-limit handling is integrated into the adapter branch, with
  entry-point regressions for rejected deep exports, supported nested metadata
  and unexpected internal errors. Real-export validation remains outstanding.
- Add a LightEval adapter after validating current result schemas.

## More useful CI reports
- Nonstandard NaN/Infinity tokens: rejected across run/policy files, including
  ignored fields, without changing comparison semantics or exact-byte audits.
- JSON decoder nesting-limit failures: handled as input errors across run and
  policy files, with exit 2 and no partial report in every output format.
- Per-metric absolute tolerances: implemented via `--metric-tolerances`.
- Explicit direction policies: implemented via `--metric-directions`; conflicts
  with either run are rejected rather than silently overriding metadata.
- Markdown report: implemented via `--format markdown`, with exact-byte input
  SHA-256 hashes, comparison outcomes and escaped run/metric metadata.
- Machine-readable audit: implemented via `--format json-audit`, with a versioned
  envelope containing run metadata, parsed policies and exact-byte source hashes.
  Default JSON remains unchanged; all formats use the same checks and exit codes.
- Sample-ID fingerprints: implemented for optional per-result `sample_ids`,
  detecting changes hidden by equal sample counts. Content verification remains
  outside the scope of this identity check.
- Paired sample-level comparisons with seeded bootstrap intervals. Do not infer
  significance from aggregate scores alone.

## Edge AI extension
- Import measurements from CPU/Raspberry Pi inference runs.
- Record warm-up, latency percentiles, hardware and runtime configuration.
- Compare accuracy against latency and memory without mixing unlike protocols.

## Contribution queue inspected

Initial inspection: 2026-10-17 UTC. This is a focused shortlist, not an exhaustive
survey or a promise that issues remain available.

1. https://github.com/EleutherAI/lm-evaluation-harness/issues/1883 — regression
   testing request. Inspect current tests and linked PRs before choosing scope.
2. https://github.com/EleutherAI/lm-evaluation-harness/issues/2552 — math answer
   extraction. Reproduce against current HEAD and check whether already fixed.
3. https://github.com/huggingface/lighteval/issues/804 — result counts. A prior
   PR (#1187) and multiple interested contributors are recorded in the thread;
   do not submit a duplicate implementation without resolving overlap.
4. https://github.com/huggingface/lighteval/issues/1056 — long-horizon evaluation.
   Requires dataset/license review and a validated scoring protocol.

For upstream work: read repository instructions and AI policy, check current
issue/PR activity, reproduce the problem, make the smallest useful patch, test it,
and submit through a fork. Do not claim a merged contribution until it is merged.

No upstream patch or PR has been submitted during this initial preparation.
