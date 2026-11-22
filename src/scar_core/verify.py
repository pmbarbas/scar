"""Read-only evidence loading and verifier interface. No plugins are imported from input."""

from __future__ import annotations
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
from typing import Any, Protocol
from .contracts import ScarInputError, parse_json_bytes
from .secureio import open_relative_regular, open_root, read_bounded_fd

MAX_EVIDENCE_BYTES = 65_536


@dataclass(frozen=True)
class EvidencePayload:
    evidence_id: str
    obligation_id: str
    source_tree_digest: str
    source_epoch: int
    observed: bool
    test_id: str
    sha256: str
    path: str


@dataclass(frozen=True)
class VerificationResult:
    verified_polarity: str | None
    reason_code: str
    detail: str
    evidence_integrity: bool
    independent: bool


class EvidenceVerifier(Protocol):
    """Host-selected verifier protocol; only a trusted implementation may assert semantic validity.

    ``independent`` and ``evidence_integrity`` are required admission attestations
    returned by that implementation. Claim metadata and matching hashes are not
    authentication of the verifier or its authority.
    """

    verifier_id: str

    def verify(
        self,
        *,
        evidence: EvidencePayload,
        claim: dict[str, Any],
        scope: dict[str, Any],
        policy: dict[str, Any],
    ) -> VerificationResult: ...


def load_evidence(root: Path, reference: dict[str, Any]) -> EvidencePayload:
    root_fd = open_root(root)
    try:
        fd = open_relative_regular(root_fd, reference["path"])
    finally:
        os.close(root_fd)
    try:
        raw = read_bounded_fd(fd, MAX_EVIDENCE_BYTES, "EVIDENCE_TOO_LARGE")
    finally:
        os.close(fd)
    actual = hashlib.sha256(raw).hexdigest()
    if actual != reference["sha256"]:
        raise ScarInputError("EVIDENCE_DIGEST_MISMATCH", "evidence digest does not match")
    try:
        data = parse_json_bytes(raw)
    except ScarInputError as exc:
        raise ScarInputError("EVIDENCE_RECORD_INVALID", "evidence JSON is invalid") from exc
    if not isinstance(data, dict):
        raise ScarInputError(
            "EVIDENCE_RECORD_INVALID", "evidence record must be an object"
        )
    required = {
        "schema",
        "evidence_id",
        "obligation_id",
        "source_epoch",
        "source_tree_digest",
        "observed",
        "test_id",
    }
    if set(data) != required:
        raise ScarInputError(
            "EVIDENCE_SCHEMA_INVALID", "evidence record fields do not match schema"
        )
    if data["schema"] != "scar.fixture.evidence.v1" or not isinstance(
        data["observed"], bool
    ):
        raise ScarInputError(
            "EVIDENCE_SCHEMA_INVALID", "invalid evidence record schema/value"
        )
    if (
        data["evidence_id"] != reference["evidence_id"]
        or data["obligation_id"]
        != reference.get("obligation_id", data["obligation_id"])
        or data["source_epoch"] != reference["source_epoch"]
        or data["source_tree_digest"] != reference["source_tree_digest"]
    ):
        # obligation_id is carried by claim/rule rather than the wire reference in v0.
        if (
            data["evidence_id"] != reference["evidence_id"]
            or data["source_epoch"] != reference["source_epoch"]
            or data["source_tree_digest"] != reference["source_tree_digest"]
        ):
            raise ScarInputError(
                "EVIDENCE_BINDING_MISMATCH",
                "record identity/scope does not match reference",
            )
    return EvidencePayload(
        data["evidence_id"],
        data["obligation_id"],
        data["source_tree_digest"],
        data["source_epoch"],
        data["observed"],
        data["test_id"],
        actual,
        reference["path"],
    )


class DigestOnlyVerifier:
    """Integrity-only default: a digest match never becomes semantic support."""

    verifier_id = "digest-only-v1"

    def verify(
        self,
        *,
        evidence: EvidencePayload,
        claim: dict[str, Any],
        scope: dict[str, Any],
        policy: dict[str, Any],
    ) -> VerificationResult:
        return VerificationResult(
            None,
            "NO_TRUSTED_SEMANTIC_VERIFIER",
            "bytes match their digest; digest alone does not verify the asserted result",
            True,
            False,
        )
