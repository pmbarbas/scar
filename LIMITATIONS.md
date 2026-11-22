# Limitations

- Experimental offline reference implementation. It is not production-ready and does not make resume/execute/authorize decisions.
- The default digest-only verifier checks byte equality with a supplied digest. Hashes do not authenticate their source or establish semantic truth.
- A host-injected verifier is trusted by the caller; the `independent` flag is an assertion, not a cryptographic identity credential.
- `scar-kit test` is a deterministic bundled smoke fixture. `inspect` and `explain` accept only SCAR's bounded evidence envelope, not arbitrary logs.
- The bundled demo oracle is fixture-specific. It must not be generalized to other repositories or workflows.
- The program does not read source repositories, execute agent code, make network calls, mutate user files, or grant permissions.
- Secure descriptor-relative file access is supported only on POSIX hosts exposing the required `openat`-style Python facilities. Other systems fail closed. Filesystems with unusual semantics, privileged attackers, hard-link provenance, compromised kernels, and resource exhaustion beyond the configured byte/row/state caps have not been fully qualified.
- A directory writable by an attacker can still change ordinary in-root files. Descriptor pinning prevents symlink escape and path redirection at open; it is not a snapshot or immutability guarantee. A digest check detects content differing from the envelope's declared digest.
- Only bounded synthetic security fixtures and the documented historical evidence were tested. No production traces, external users, community contributors, adoption, market value, or ROI were measured.
- CRT/sheaf/lattice combination did not show incremental advantage. The project claims no new theorem, superiority, patent, or freedom to operate.
- The project is distributed under Apache License, Version 2.0; that licence does not imply production readiness, security certification, or any support commitment.
- No support SLA, maintainer response-time promise, or stable long-term compatibility commitment exists.
