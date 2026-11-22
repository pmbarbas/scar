"""Deterministic packaged demo. Its verifier rules apply only to the bundled toy fixture."""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from .recovery import inspect_evidence
from .verify import EvidencePayload, VerificationResult

_DATA = Path(__file__).parent / "data" / "demo"


class _DemoVerifier:
    verifier_id = "scar-bundled-demo-oracle-v1"

    def __init__(self, rules: dict[str, Any]):
        self.rules = rules

    def verify(
        self,
        *,
        evidence: EvidencePayload,
        claim: dict[str, Any],
        scope: dict[str, Any],
        policy: dict[str, Any],
    ) -> VerificationResult:
        rule = self.rules.get(evidence.evidence_id)
        if not rule:
            return VerificationResult(
                None, "DEMO_RULE_MISSING", "no bundled demo rule", True, False
            )
        if (
            rule["sha256"] != evidence.sha256
            or rule["obligation_id"] != evidence.obligation_id
            or rule["tree_digest"] != evidence.source_tree_digest
            or rule["epoch"] != evidence.source_epoch
        ):
            return VerificationResult(
                None,
                "DEMO_BINDING_MISMATCH",
                "bundled evidence does not match demo rule",
                False,
                True,
            )
        polarity = "SUPPORT" if evidence.observed else "REFUTE"
        if polarity != rule["polarity"]:
            return VerificationResult(
                None,
                "DEMO_SEMANTIC_MISMATCH",
                "source observation differs from bundled demo ground truth",
                True,
                True,
            )
        return VerificationResult(
            polarity,
            "DEMO_VERIFIED",
            "bundled deterministic example oracle accepted this fixture record",
            True,
            True,
        )


def run_demo() -> tuple[dict[str, Any], str]:
    env = json.loads((_DATA / "envelope.json").read_text(encoding="utf-8"))
    rules = json.loads((_DATA / "verifier_rules.json").read_text(encoding="utf-8"))[
        "rules"
    ]
    assessment = inspect_evidence(
        env, _DATA, _DemoVerifier(rules), env["policy"]
    ).to_dict()
    story = (
        "A coordinator restarted on H9. O1–O3 have current fixture-verified evidence; an old H8 success for O4 is stale. "
        "SCAR proposes a fresh O4 verification request. This bundled deterministic demonstration is not execution authority."
    )
    return assessment, story
