# Research note: evidence-coherent agent workflow recovery

## Question and contract

SCAR asks what a local coordinator may conclude after a multi-agent workflow is interrupted and restarted against a changed state. Its input contract separates obligation claims, evidence references, source epoch/tree identity, event causality, verifier assertions, and host policy. The implementation enumerates a bounded set of feasible Boolean obligation states (at most eight obligations / 256 assignments), retains unknowns, blocks completion when evidence is stale or causally incomplete, and returns advisory verification requests. It is a research reference, not a general workflow runtime.

## Mathematical structures investigated

The project investigated four interacting descriptions: CRT residue channels for redundant source-anchored state; finite cellular sheaves for compatibility of local agent observations; evidence bilattices for separate positive and negative support; and geometric lattice decoding only when an explicit numeric noise model exists. The concrete experiments did not establish a new theorem or a useful three-way runtime mechanism.

Finite relational sheaf gluing in the tested finite model reduces to satisfiability of the corresponding local relations, so an ordinary CSP/SAT implementation has the same information. A scalar completed-count is not decision-sufficient: distinct obligation assignments can share the same count while differing in unmet prerequisites and next justified queries. The exact identity ambiguity example is `C(29,23) = 475,020`: for 29 labeled obligations, a count of 23 does not identify which six are incomplete. This is elementary combinatorics, not a novel theorem.

The finite 50-bit CRT construction and same-information ECC comparator are recorded in the accepted FEAS research record. This note does not redistribute that dataset or claim its independent re-execution from this small fixture. The accepted comparison found no demonstrated advantage for the CRT construction under its stated bounded channel assumptions. Conventional error correction addresses transmission faults; it does not establish semantic correctness of an agent's claim.

## Baselines, observations, and negative findings

Accepted historical records report original SCAR/CSP parity on 31 cases, an R1 corrective suite of 15 cases, 48 generated DEV01 incidents, and an INT01 local workflow comparison of six command outcomes. In INT01, semantic task correctness was UNKNOWN. These are source/authenticity-labeled project results, not a single unified benchmark, real customer traffic, or complete replication from this archive. The PUB-00 bounded timings found the SCAR execution path slower than the native conventional path on the measured machine (cold 31.368 ms vs 28.694 ms; warm 2.429 ms vs 1.437 ms). They do not establish general performance.

The scientific conclusion remains: CRT/sheaf/lattice incremental superiority and technical novelty are not supported; finite sheaf gluing was CSP-equivalent in the tested model; geometric lattice decoding lacks an admitted runtime noise channel; and conventional event-log/CSP recovery tied outcome quality in studied cases. Consumer value, market adoption, and commercial ROI remain unmeasured.

## Prior art and attribution

This project does not claim to originate distributed consistent cuts, sheaf theory, CRT, error-correcting codes, or CSP. Chandy and Lamport describe consistent global snapshots in distributed systems (ACM TOCS 3(1), 1985, [original paper](https://lamport.azurewebsites.net/pubs/chandy.pdf)). Hansen and Ghrist develop spectral methods for cellular sheaves ([J. Applied and Computational Topology, 2019, DOI](https://doi.org/10.1007/s41468-019-00038-7)). Wang and Xia analyze robust CRT with common-factor moduli and bounded remainder error ([IEEE Transactions on Signal Processing 58(11), 2010, DOI](https://doi.org/10.1109/TSP.2010.2066974)). Shannon's foundational communication-theory paper frames channel coding and information limits ([Bell System Technical Journal, 1948, DOI](https://doi.org/10.1002/j.1538-7305.1948.tb01338.x)). These references establish context, not novelty or a direct comparison with SCAR.

## Reproducibility boundary

Run `./ci/verify_release_candidate.sh` from this repository root. It checks package installation, CLI fixtures, tests, and the security regressions included here. Historical P00–P04/FEAS raw records, custody bundles, and source handoffs are not included. This archive reproduces the code and bounded synthetic tests, not every historical numeric result.

## Open questions suitable for contributions

- Can authentic, privacy-safe workflow traces support independent semantic ground truth?
- Can a verifier interface authenticate verifier identity and bind checks to source state without claiming more than it proves?
- Which interoperability envelope and provenance contract are useful across actual agent frameworks?
- Under what explicitly modeled communication fault channel could residue redundancy add value over conventional ECC?
- What recovery decisions remain genuinely decision-insufficient under a competent event-log/CSP baseline?
