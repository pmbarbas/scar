"""Small installed-package recovery smoke kit; no inference code is duplicated."""
from __future__ import annotations

from typing import Any


def run_kit() -> dict[str, Any]:
    """Check the accepted bundled fixture and core trust fail-closed contract."""
    from scar_core import DigestOnlyVerifier, EvidencePayload, validate_assessment_roundtrip
    from scar_core.demo import run_demo

    assessment, _story = run_demo()
    if assessment.get("outcome") != "STALE_EPOCH":
        raise AssertionError("bundled example no longer exposes the expected stale epoch")
    if not assessment.get("host_authorization_required"):
        raise AssertionError("host authorization boundary missing")
    if "O4-integration" not in assessment.get("unresolved_obligations", []):
        raise AssertionError("stale O4 must remain unresolved")
    recommendation = assessment.get("recommendations", [{}])[0]
    if recommendation.get("query_id") != "verify-O4-integration":
        raise AssertionError("expected fresh O4 verification request was not produced")
    validate_assessment_roundtrip(assessment)

    payload = EvidencePayload(
        evidence_id="kit-smoke", obligation_id="kit-smoke", source_tree_digest="0" * 64,
        source_epoch=1, observed=True, test_id="digest-only-negative", sha256="0" * 64, path="smoke.json",
    )
    digest_result = DigestOnlyVerifier().verify(
        evidence=payload,
        claim={"claim_id": "kit-smoke", "polarity": "SUPPORT"},
        scope={"epoch": 1, "tree_digest": "0" * 64}, policy={},
    )
    if digest_result.verified_polarity is not None or digest_result.independent:
        raise AssertionError("digest-only verifier must not claim semantic support")
    return {
        "status": "PASS",
        "checks": ["bundled_demo_stale_epoch", "host_authorization_required", "recovery_request", "assessment_roundtrip", "digest_only_abstains"],
        "core_outcome": assessment["outcome"],
        "semantic_scope": "bundled fixture only; not a general source verifier",
    }

