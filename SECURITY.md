# Security policy

SCAR handles bounded local JSON evidence and is experimental. Do not use its output as authorization, a security decision, or proof of semantic correctness. The library does not execute workflow content, call the network, or write to user-selected evidence paths.

The package uses descriptor-relative POSIX opens with no-follow checks for each root and evidence path component, validates the opened descriptor as a regular file, and reads at most the configured cap plus one byte. Unsupported platforms fail closed. This reduces path-redirection exposure; it does not make a concurrently writable evidence tree immutable and does not defend against a compromised host, kernel, or malicious privileged process.

CLI diagnostics use stable reason codes and redact user-controlled identity fields to local aliases. Library callers receive structured identifiers from the assessment API and must protect those values in their own logs and user interfaces. Evidence and envelope byte limits, schema limits, and the eight-obligation state cap remain in force.

Security vulnerabilities should be submitted through [GitHub private vulnerability reporting](https://github.com/pmbarbas/scar/security/advisories/new), which must be enabled on this repository at publication. Do not send sensitive evidence through public issues. No response-time commitment is made.
