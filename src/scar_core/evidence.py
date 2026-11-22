"""Evidence admission with explicit causal, policy and verifier controls."""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from .contracts import ScarInputError
from .causality import CausalReport, claim_has_complete_cut
from .verify import EvidenceVerifier, load_evidence


@dataclass(frozen=True)
class ClaimFinding:
    claim_id: str
    obligation_id: str
    verified_polarity: str | None
    status: str
    reason_code: str
    evidence_ids: tuple[str, ...]
    verifier_ids: tuple[str, ...]
    origin_authenticated: bool
    independent: bool


def _unverified(claim: dict[str, Any], reason: str) -> ClaimFinding:
    return ClaimFinding(
        claim["claim_id"],
        claim["obligation_id"],
        None,
        "UNVERIFIED",
        reason,
        tuple(claim["evidence_ids"]),
        (),
        claim["origin_authenticated"],
        False,
    )


def resolve_claims(
    envelope: dict[str, Any],
    root: Path,
    verifier: EvidenceVerifier,
    causal: CausalReport,
) -> tuple[
    tuple[ClaimFinding, ...], tuple[dict[str, Any], ...], tuple[dict[str, Any], ...]
]:
    scope = envelope["scope"]
    evidence_by_id = {row["evidence_id"]: row for row in envelope["evidence"]}
    obligation_by_id = {row["obligation_id"]: row for row in envelope["obligations"]}
    findings = []
    stale = []
    causal_missing = list(causal.missing_parents) + list(causal.claim_event_errors)
    host_policy_id = envelope["policy"]["policy_id"]
    policy_scope_matches = scope["verifier_policy_id"] == host_policy_id

    for claim in sorted(envelope["claims"], key=lambda row: row["claim_id"]):
        cid = claim["claim_id"]
        oid = claim["obligation_id"]
        if (
            claim["asserted_epoch"] != scope["epoch"]
            or claim["asserted_tree_digest"] != scope["tree_digest"]
        ):
            stale.append(
                {
                    "claim_id": cid,
                    "obligation_id": oid,
                    "claim_epoch": claim["asserted_epoch"],
                    "current_epoch": scope["epoch"],
                    "claim_tree_digest": claim["asserted_tree_digest"],
                    "current_tree_digest": scope["tree_digest"],
                    "reason_code": "STALE_SOURCE_SCOPE",
                }
            )
            findings.append(
                ClaimFinding(
                    cid,
                    oid,
                    None,
                    "STALE",
                    "STALE_SOURCE_SCOPE",
                    tuple(claim["evidence_ids"]),
                    (),
                    claim["origin_authenticated"],
                    False,
                )
            )
            continue

        if not policy_scope_matches:
            findings.append(_unverified(claim, "VERIFIER_POLICY_BINDING_MISMATCH"))
            continue

        if claim["event_id"] not in {event["event_id"] for event in envelope["events"]}:
            causal_missing.append(
                {
                    "claim_id": cid,
                    "event_id": claim["event_id"],
                    "reason_code": "CLAIM_EVENT_MISSING",
                }
            )
        if not claim_has_complete_cut(claim, causal):
            paths = [
                row
                for row in causal.incomplete_event_causes
                if row["event_id"] == claim["event_id"]
            ]
            if paths:
                for path in paths:
                    causal_missing.append(
                        {
                            "claim_id": cid,
                            "event_id": claim["event_id"],
                            "root_event_id": path["root_event_id"],
                            "root_reason_code": path["root_reason_code"],
                            "causal_path": path["causal_path"],
                            "reason_code": "INCOMPLETE_CAUSAL_CUT",
                        }
                    )
            else:
                causal_missing.append(
                    {
                        "claim_id": cid,
                        "event_id": claim["event_id"],
                        "reason_code": "INCOMPLETE_CAUSAL_CUT",
                    }
                )
            findings.append(
                ClaimFinding(
                    cid,
                    oid,
                    None,
                    "INCOMPLETE_CAUSAL",
                    "INCOMPLETE_CAUSAL_CUT",
                    tuple(claim["evidence_ids"]),
                    (),
                    claim["origin_authenticated"],
                    False,
                )
            )
            continue

        obligation = obligation_by_id[oid]
        if not claim["evidence_ids"]:
            findings.append(_unverified(claim, "CLAIM_WITHOUT_EVIDENCE"))
            continue

        polarity_set: set[str] = set()
        reason = "VERIFIER_RESULT_INVALID"
        verifier_ids = []
        all_admitted = True
        all_independent = True
        refs = []

        for evidence_id in claim["evidence_ids"]:
            ref = evidence_by_id.get(evidence_id)
            if ref is None:
                reason = "EVIDENCE_REFERENCE_MISSING"
                all_admitted = False
                continue
            accepted_classes = set(obligation["accepted_evidence_classes"])
            if ref["evidence_class"] not in accepted_classes:
                reason = "EVIDENCE_CLASS_NOT_ACCEPTED"
                all_admitted = False
                continue
            if (
                ref["source_epoch"] != scope["epoch"]
                or ref["source_tree_digest"] != scope["tree_digest"]
            ):
                stale.append(
                    {
                        "claim_id": cid,
                        "evidence_id": evidence_id,
                        "obligation_id": oid,
                        "evidence_epoch": ref["source_epoch"],
                        "current_epoch": scope["epoch"],
                        "reason_code": "STALE_EVIDENCE_SCOPE",
                    }
                )
                reason = "STALE_EVIDENCE_SCOPE"
                all_admitted = False
                continue
            try:
                payload = load_evidence(root, ref)
            except ScarInputError as exc:
                reason = exc.code
                all_admitted = False
                continue
            if payload.obligation_id != oid:
                reason = "EVIDENCE_OBLIGATION_MISMATCH"
                all_admitted = False
                continue
            if (
                payload.source_epoch != claim["asserted_epoch"]
                or payload.source_tree_digest != claim["asserted_tree_digest"]
            ):
                stale.append(
                    {
                        "claim_id": cid,
                        "evidence_id": evidence_id,
                        "obligation_id": oid,
                        "reason_code": "CLAIM_EVIDENCE_SCOPE_MISMATCH",
                    }
                )
                reason = "CLAIM_EVIDENCE_SCOPE_MISMATCH"
                all_admitted = False
                continue
            try:
                result = verifier.verify(
                    evidence=payload,
                    claim=claim,
                    scope=scope,
                    policy=envelope["policy"],
                )
                polarity = result.verified_polarity
                integrity = result.evidence_integrity
                independent = result.independent
                verifier_reason = result.reason_code
            except Exception:
                reason = "VERIFIER_ERROR"
                all_admitted = False
                all_independent = False
                continue

            verifier_ids.append(
                getattr(verifier, "verifier_id", "host-injected-verifier")
            )
            if polarity not in ("SUPPORT", "REFUTE"):
                reason = (
                    verifier_reason
                    if isinstance(verifier_reason, str) and verifier_reason
                    else "NO_VERIFIED_POLARITY"
                )
                all_admitted = False
                if independent is not True:
                    all_independent = False
                continue
            if type(integrity) is not bool or integrity is not True:
                reason = "EVIDENCE_INTEGRITY_UNCONFIRMED"
                all_admitted = False
                continue
            if type(independent) is not bool or independent is not True:
                reason = "VERIFIER_NOT_INDEPENDENT"
                all_admitted = False
                all_independent = False
                continue
            polarity_set.add(polarity)
            refs.append(evidence_id)
            if claim["polarity"] != polarity:
                reason = "ASSERTION_EVIDENCE_MISMATCH"

        if not all_admitted:
            findings.append(
                ClaimFinding(
                    cid,
                    oid,
                    None,
                    "UNVERIFIED",
                    reason,
                    tuple(refs),
                    tuple(sorted(set(verifier_ids))),
                    claim["origin_authenticated"],
                    False,
                )
            )
            continue
        if len(polarity_set) > 1:
            findings.append(
                ClaimFinding(
                    cid,
                    oid,
                    None,
                    "CONFLICTING_EVIDENCE",
                    "CLAIM_EVIDENCE_POLARITY_CONFLICT",
                    tuple(refs),
                    tuple(sorted(set(verifier_ids))),
                    claim["origin_authenticated"],
                    all_independent,
                )
            )
            continue
        verified = next(iter(polarity_set))
        mismatch = (
            "ASSERTION_EVIDENCE_MISMATCH"
            if claim["polarity"] != verified
            else "VERIFIED"
        )
        findings.append(
            ClaimFinding(
                cid,
                oid,
                verified,
                "VERIFIED",
                mismatch,
                tuple(refs),
                tuple(sorted(set(verifier_ids))),
                claim["origin_authenticated"],
                all_independent,
            )
        )

    stale_sorted = tuple(
        sorted(
            stale,
            key=lambda row: (
                row.get("claim_id", ""),
                row.get("evidence_id", ""),
                row["reason_code"],
            ),
        )
    )
    causal_sorted = tuple(
        sorted(
            causal_missing,
            key=lambda row: (
                row.get("event_id", ""),
                row.get("claim_id", ""),
                row["reason_code"],
                row.get("root_event_id", ""),
            ),
        )
    )
    return tuple(findings), stale_sorted, causal_sorted
