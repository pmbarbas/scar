"""Bounded, deterministic evidence-state recovery. Pure read-only; no executor exists."""

from __future__ import annotations
from itertools import product
from pathlib import Path
from typing import Any
from .causality import analyze_causality
from .contracts import OUTPUT_SCHEMA, RecoveryAssessment, validate_envelope
from .evidence import resolve_claims
from .verify import EvidenceVerifier


def _enumerate_states(
    obligations: list[dict[str, Any]], findings: tuple[Any, ...], cap: int
) -> list[dict[str, bool]]:
    ids = [o["obligation_id"] for o in obligations]
    if 2 ** len(ids) > cap:
        return []
    polarity: dict[str, set[str]] = {oid: set() for oid in ids}
    for f in findings:
        if f.status == "VERIFIED" and f.verified_polarity:
            polarity[f.obligation_id].add(f.verified_polarity)
    out = []
    for bits in product((False, True), repeat=len(ids)):
        candidate = dict(zip(ids, bits))
        invalid = False
        for oid, values in polarity.items():
            if values == {"SUPPORT"} and candidate[oid] is not True:
                invalid = True
            if values == {"REFUTE"} and candidate[oid] is not False:
                invalid = True
            # BOTH is deliberately left ambiguous; it is separately surfaced as a conflict.
        if invalid:
            continue
        for row in obligations:
            if candidate[row["obligation_id"]] and any(
                not candidate[d] for d in row["depends_on"]
            ):
                invalid = True
                break
        if not invalid:
            out.append(candidate)
        if len(out) > cap:
            return []
    return out


def _completed(
    ids: list[str],
    dependencies: dict[str, list[str]],
    support: dict[str, bool],
    conflicts: set[str],
) -> list[str]:
    done = set()
    changed = True
    while changed:
        changed = False
        for oid in ids:
            if (
                oid not in done
                and oid not in conflicts
                and support.get(oid, False)
                and all(d in done for d in dependencies[oid])
            ):
                done.add(oid)
                changed = True
    return [oid for oid in ids if oid in done]


def _recommend(
    env: dict[str, Any],
    states: list[dict[str, bool]],
    unresolved: list[str],
    completed: list[str],
    has_diagnostics: bool,
) -> tuple[list[dict[str, Any]], str | None]:
    if len(completed) == len(env["obligations"]) and not has_diagnostics:
        return (
            [
                {
                    "kind": "ADVISORY",
                    "action": "MAY_CONTINUE",
                    "authorization": "HOST_DECISION_REQUIRED",
                    "evidence_refs": [c["claim_id"] for c in env["claims"]],
                }
            ],
            None,
        )
    eligible = []
    dependencies = {o["obligation_id"]: o["depends_on"] for o in env["obligations"]}
    for q in env["policy"]["allowed_queries"]:
        oid = q["obligation_id"]
        if oid not in unresolved or any(
            dep not in completed for dep in dependencies[oid]
        ):
            continue
        true_count = sum(1 for s in states if s.get(oid, False))
        false_count = len(states) - true_count
        allowed = set(q["allowed_outcomes"])
        partitions = []
        if "SUPPORT" in allowed:
            partitions.append(true_count)
        if "REFUTE" in allowed:
            partitions.append(false_count)
        if not partitions:
            continue
        # Response-conditional minimax; timeout/unknown is explicit and retains all states.
        score = (max(partitions), q["cost"], q["query_id"])
        eligible.append((score, q, partitions))
    if not eligible:
        return ([], "NO_PERMITTED_SEPARATING_QUERY" if states else "NO_FEASIBLE_STATE")
    score, q, parts = min(eligible, key=lambda x: x[0])
    return (
        [
            {
                "kind": "EVIDENCE_REQUEST",
                "query_id": q["query_id"],
                "obligation_id": q["obligation_id"],
                "declared_cost": q["cost"],
                "cost_units": "host-declared, not empirically calibrated",
                "response_conditional_worst_case_states": score[0],
                "outcome_partitions": {
                    "SUPPORT": sum(1 for s in states if s[q["obligation_id"]]),
                    "REFUTE": sum(1 for s in states if not s[q["obligation_id"]]),
                },
                "timeout_branch": {
                    "result": "UNKNOWN_TIMEOUT",
                    "feasible_states_retained": len(states),
                    "fallback": "ABSTAIN",
                },
                "host_authorization_required": True,
            }
        ],
        None,
    )


def inspect_evidence(
    envelope: dict[str, Any],
    root: str | Path,
    verifier: EvidenceVerifier,
    policy: dict[str, Any],
) -> RecoveryAssessment:
    """Inspect an envelope using an injected verifier and caller-owned policy; performs no writes."""
    env = validate_envelope(envelope)
    if policy != env["policy"]:
        # Avoid evaluating a different policy from the one surfaced in the input/report.
        raise ValueError("policy argument must equal the validated envelope policy")
    causal = analyze_causality(env)
    findings, stale, causal_missing = resolve_claims(env, Path(root), verifier, causal)
    ids = [o["obligation_id"] for o in env["obligations"]]
    deps = {o["obligation_id"]: o["depends_on"] for o in env["obligations"]}
    direct: dict[str, set[str]] = {oid: set() for oid in ids}
    claim_refs: dict[str, dict[str, list[str]]] = {
        oid: {"SUPPORT": [], "REFUTE": []} for oid in ids
    }
    conflicts = []
    invalid = []
    for f in findings:
        if f.status == "VERIFIED" and f.verified_polarity:
            direct[f.obligation_id].add(f.verified_polarity)
            claim_refs[f.obligation_id][f.verified_polarity].append(f.claim_id)
            if f.reason_code == "ASSERTION_EVIDENCE_MISMATCH":
                invalid.append(
                    {
                        "claim_id": f.claim_id,
                        "obligation_id": f.obligation_id,
                        "reason_code": f.reason_code,
                        "detail": "claim assertion disagrees with independently verified source result",
                    }
                )
        else:
            invalid.append(
                {
                    "claim_id": f.claim_id,
                    "obligation_id": f.obligation_id,
                    "reason_code": f.reason_code,
                    "detail": f.status,
                }
            )
    conflicts_set = {oid for oid in ids if direct[oid] == {"SUPPORT", "REFUTE"}}
    for oid in ids:
        if oid in conflicts_set:
            conflicts.append(
                {
                    "obligation_id": oid,
                    "reason_code": "VERIFIED_SUPPORT_AND_REFUTATION",
                    "support_claim_ids": sorted(claim_refs[oid]["SUPPORT"]),
                    "refute_claim_ids": sorted(claim_refs[oid]["REFUTE"]),
                }
            )
    support = {oid: (direct[oid] == {"SUPPORT"}) for oid in ids}
    completed = _completed(ids, deps, support, conflicts_set)
    states = _enumerate_states(
        env["obligations"], findings, env["policy"]["max_states"]
    )
    unresolved = [oid for oid in ids if oid not in completed]
    diagnostics = bool(stale or causal_missing or conflicts or invalid)
    policy_binding_invalid = any(
        x["reason_code"] == "VERIFIER_POLICY_BINDING_MISMATCH" for x in invalid
    )
    recommendations: list[dict[str, Any]]
    abstain: str | None
    if policy_binding_invalid:
        recommendations, abstain = [], "VERIFIER_POLICY_BINDING_MISMATCH"
    else:
        recommendations, abstain = _recommend(
            env, states, unresolved, completed, diagnostics
        )
    if conflicts:
        outcome = "CONFLICTING_EVIDENCE"
    elif causal_missing:
        outcome = "INCOMPATIBLE_CAUSAL_HISTORY"
    elif stale:
        outcome = "STALE_EPOCH"
    elif not states:
        outcome = "AMBIGUOUS_STATES"
    elif len(completed) == len(ids):
        outcome = "SUPPORTED_STATE"
    elif len(states) > 1:
        outcome = "AMBIGUOUS_STATES"
    elif invalid:
        outcome = "INSUFFICIENT_EVIDENCE"
    else:
        outcome = "PARTIAL_STATE"
    if recommendations:
        status = "SUPPORTED_STATE" if outcome == "SUPPORTED_STATE" else "PARTIAL_STATE"
    else:
        status = outcome
    if not recommendations and abstain is None:
        abstain = "NO_USEFUL_COMMON_ACTION"
    states_out = []
    for oid in ids:
        vals = direct[oid]
        label = (
            "BOTH"
            if vals == {"SUPPORT", "REFUTE"}
            else "SUPPORTED"
            if vals == {"SUPPORT"}
            else "REFUTED"
            if vals == {"REFUTE"}
            else "NEITHER"
        )
        states_out.append(
            {
                "obligation_id": oid,
                "evidence_state": label,
                "support_claim_ids": sorted(claim_refs[oid]["SUPPORT"]),
                "refute_claim_ids": sorted(claim_refs[oid]["REFUTE"]),
                "completed": oid in completed,
                "dependencies": deps[oid],
                "reason_codes": ["DEPENDENCIES_NOT_COMPLETED"]
                if vals == {"SUPPORT"}
                and oid not in completed
                and oid not in conflicts_set
                else [],
            }
        )
    possible = set()
    for q in [] if policy_binding_invalid else env["policy"]["allowed_queries"]:
        oid = q["obligation_id"]
        if oid in unresolved and all(dep in completed for dep in deps[oid]):
            possible.add(q["query_id"])
    if len(completed) == len(ids) and not diagnostics:
        possible.add(env["policy"]["advisory_when_complete"])
    possible_actions = tuple(sorted(possible))
    refs = tuple(sorted({eid for c in env["claims"] for eid in c["evidence_ids"]}))
    assumptions = (
        "Verifier result is trusted only to the extent its caller supplies a trusted verifier.",
        "A matching digest binds bytes but does not establish origin or semantic truth.",
        "Claim origin_authenticated and verifier_id values are untrusted metadata, not authority or provenance proofs.",
        "The injected verifier must independently attest semantic verification and evidence integrity for every accepted reference.",
        "Envelope/scope policy IDs are checked for consistency with the host-supplied policy but are not cryptographic credentials.",
        "All recommendations are advisory and require host authorization.",
        "Timeout and unknown outcomes preserve the feasible-state set and cause abstention.",
    )
    return RecoveryAssessment(
        OUTPUT_SCHEMA,
        env["workflow_id"],
        status,
        outcome,
        dict(env["scope"]),
        tuple(states_out),
        tuple(completed),
        tuple(unresolved),
        tuple(conflicts),
        tuple(stale),
        tuple(causal_missing),
        tuple(sorted(invalid, key=lambda x: (x.get("claim_id", ""), x["reason_code"]))),
        len(states),
        env["policy"]["max_states"],
        tuple(states),
        possible_actions,
        tuple(recommendations),
        abstain,
        refs,
        env["policy"]["policy_id"],
        assumptions,
        True,
    )
