# SCAR Research Toolkit

**Experimental research software; not a production recovery or authorization system.** Released under the Apache License, Version 2.0 (see [LICENSE](LICENSE)). SCAR is a local Python toolkit for inspecting structured evidence from interrupted agent workflows, demonstrating bounded recovery assessments, and exercising evidence-trust failure cases. It does not execute workflow code, run agents, make network calls, write to user paths, or grant permission.

The tested claim is narrow: given a versioned SCAR envelope, bounded source evidence, and a host-selected verifier, the library produces a deterministic advisory assessment that preserves stale, contradictory, incomplete, and unverified states. Its default verifier only checks byte digests; it does not establish who produced evidence or whether evidence is semantically true.

## 90-second local demo

From the repository root with Python 3.11 or newer:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install --no-index --no-build-isolation .
scar-kit demo
```

The bundled fixture has current evidence at H9 and an old H8 success for O4. The demo reports `STALE_EPOCH`, leaves O4 unresolved, and recommends a fresh O4 evidence request. An unknown or timed-out response retains uncertainty and requires abstention. The fixture verifier is a toy oracle bound only to the included fixture. This output is not evidence that an arbitrary workflow is safe to resume.

To run the deterministic bundled smoke fixture:

```sh
scar-kit test
```

`test` is one deterministic smoke fixture, not a universal agent-workflow test framework. `inspect` and `explain` accept the SCAR-specific evidence envelope, not arbitrary third-party logs. CLI output replaces identity fields with local aliases; library callers remain responsible for protecting returned assessment data.

To inspect a local SCAR envelope without writing files:

```sh
scar-kit inspect --input path/to/envelope.json --root path/to/evidence --format json
scar-kit explain --input path/to/envelope.json --root path/to/evidence
```

The root path is host-selected and must be an ordinary directory path with no symlink component on supported POSIX hosts. The package fails closed when the required descriptor-relative no-follow facilities are unavailable.

## Research result in brief

The project studied evidence-coherent agentic state reconstruction using CRT, finite cellular-sheaf consistency/CSP constraints, evidence bilattices, and conditional lattice decoding. The combined mechanisms did **not** demonstrate incremental advantage. Under the tested finite model, sheaf gluing is CSP-equivalent; geometric lattice decoding is inadmissible without a justified numeric noise channel; CRT correction did not outperform an equal-information ECC comparator. A conventional event-log/CSP baseline tied outcome quality in the studied cases, and the measured SCAR path was slower in bounded comparisons. No external user value, commercial return, market adoption, or novel mathematical result was established.

The research record and limitations are summarized in [RESEARCH.md](RESEARCH.md) and [LIMITATIONS.md](LIMITATIONS.md). The full historical benchmark records are not included; the bundled example reproduces the code and synthetic checks, not every historical numeric result.

## Install from source and verify

The source tree and build backend use only the Python standard library. Wheel and source-distribution builds work without registry access or build plugins:

```sh
python -m pip install --no-index --no-build-isolation .
./ci/verify_release_candidate.sh
```

The CI script creates all environments and outputs inside this checkout and installs from the emitted local artifacts with `--no-index`. It runs tests, source and wheel builds, CLI smoke checks, adversarial descriptor tests, and archive-manifest checks. See [SECURITY.md](SECURITY.md) before using untrusted input.

## Scope and privacy

SCAR's input is a bounded JSON envelope plus small JSON evidence records. It does not parse arbitrary tool logs, inspect source repositories, authenticate a verifier, prove evidence origin, or determine semantic correctness without a trusted verifier supplied by the host. It emits advisory recommendations only; the host must make every operational decision.

The bundled fixture is synthetic and contains no real workflow record. Historical benchmark raw records and source handoffs are not included. This source tree contains no production workflow records or external datasets.

## Contributions and maintenance

Useful contributions include interoperable adapters, authentic observable recovery workloads, independent verifier designs, causal evidence contracts, usability work, explicit fault models, fair baseline comparisons, and reproducible evaluations. Please include negative controls and avoid claiming benchmark-derived traffic is real user traffic. There is no support SLA, maintainer response-time promise, or scheduled review commitment. For security reports, use [GitHub private vulnerability reporting](https://github.com/pmbarbas/scar/security/advisories/new). Do not submit sensitive vulnerability details through public issues.

See [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).
