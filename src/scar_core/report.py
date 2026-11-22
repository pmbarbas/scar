"""Deterministic human-readable rendering for recovery assessments."""

from __future__ import annotations
from typing import Any


def render_text(result: dict[str, Any]) -> str:
    lines = [
        f"SCAR {result['outcome']} — workflow {result['workflow_id']}",
        f"Scope: repo={result['scope']['repository_id']} epoch={result['scope']['epoch']} tree={result['scope']['tree_digest']}",
        "Obligations:",
    ]
    for row in result["obligation_states"]:
        codes = ", ".join(row["reason_codes"])
        lines.append(
            f"  {row['obligation_id']}: {row['evidence_state']} (completed={str(row['completed']).lower()})"
            + (f" [{codes}]" if codes else "")
        )
    if result["stale_evidence"]:
        lines.append("Stale evidence:")
        for row in result["stale_evidence"]:
            lines.append(
                f"  {row.get('claim_id', row.get('evidence_id'))}: {row['reason_code']}"
            )
    if result["missing_causal_parents"]:
        lines.append("Causal gaps:")
        for row in result["missing_causal_parents"]:
            lines.append(
                f"  {row.get('event_id', row.get('claim_id'))}: {row['reason_code']}"
            )
    if result["conflicts"]:
        lines.append("Conflicts:")
        for row in result["conflicts"]:
            lines.append(f"  {row['obligation_id']}: {row['reason_code']}")
    if result["invalid_or_unverified_claims"]:
        lines.append("Unverified or rejected claims:")
        for row in result["invalid_or_unverified_claims"]:
            lines.append(f"  {row['claim_id']}: {row['reason_code']}")
    lines.append(
        f"Feasible interpretations: {result['feasible_state_count']} (cap={result['feasible_state_cap']})"
    )
    lines.append(
        "Possible action classes: "
        + (", ".join(result["possible_action_classes"]) or "none")
    )
    lines.append("Recommendations:")
    if not result["recommendations"]:
        lines.append(
            f"  abstain: {result['abstain_reason'] or 'NO_USEFUL_COMMON_ACTION'}"
        )
    for rec in result["recommendations"]:
        if rec["kind"] == "EVIDENCE_REQUEST":
            lines.append(
                f"  request {rec['query_id']} for {rec['obligation_id']} (cost={rec['declared_cost']}); timeout => abstain"
            )
        else:
            lines.append(
                f"  advisory {rec['action']} (host authorization still required)"
            )
    lines.append("Host authorization required: true")
    return "\n".join(lines)
