# Contributing

Contributions are welcome as proposals for adapters, privacy-safe authentic workloads, verifier contracts, causal consistency, usability, failure models, and baseline evaluation. Please distinguish synthetic traces from authentic records and report negative results.

Before opening a change:

1. Keep the runtime offline and read-only; do not execute workflow code or treat envelope text as instructions.
2. Add a focused regression fixture for each behavior change, including an adversarial negative control where applicable.
3. Run `./ci/verify_release_candidate.sh` from the repository root. It uses local artifacts only.
4. Include exact commands, interpreter versions, artifact hashes, and limitations in the report.
5. Do not add sensitive records, credentials, absolute user paths, restricted material, or unlicensed third-party content.
6. Compare claims against a competent conventional event-log/CSP baseline with identical information.

There is no guaranteed issue response, review schedule, acceptance, or maintainer support SLA. Use repository issue and pull-request workflows when available. Never attach sensitive workflow records or credentials.
