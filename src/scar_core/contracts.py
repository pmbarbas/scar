"""Strict versioned contracts for SCAR evidence envelopes and assessments."""

from __future__ import annotations
from dataclasses import dataclass
import json
from typing import Any, Mapping

INPUT_SCHEMA = "scar.evidence.v0"
OUTPUT_SCHEMA = "scar.assessment.v0"
MAX_INPUT_BYTES = 1_048_576
MAX_DEPTH = 20
MAX_OBLIGATIONS = 8
MAX_ROWS = 256
MAX_STATES = 256
HEX = frozenset("0123456789abcdef")


class ScarInputError(ValueError):
    """Invalid, unsupported, or unsafe untrusted input with a stable reason code."""

    def __init__(self, code: str, message: str):
        # Keep arbitrary identifiers, parser excerpts and path details out of
        # application logs. Consumers should branch on the stable reason code.
        safe_message = "input rejected by SCAR safety or schema checks"
        super().__init__(safe_message)
        self.code = code
        self.message = safe_message


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ScarInputError("DUPLICATE_JSON_KEY", f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _depth(value: Any, level: int = 0) -> None:
    if level > MAX_DEPTH:
        raise ScarInputError("JSON_DEPTH_LIMIT", f"JSON nesting exceeds {MAX_DEPTH}")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ScarInputError(
                    "INVALID_JSON_OBJECT", "object keys must be strings"
                )
            _depth(child, level + 1)
    elif isinstance(value, list):
        for child in value:
            _depth(child, level + 1)


def parse_json_bytes(data: bytes) -> Any:
    if len(data) > MAX_INPUT_BYTES:
        raise ScarInputError(
            "INPUT_TOO_LARGE", f"input exceeds {MAX_INPUT_BYTES} bytes"
        )
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs_no_duplicates)
    except ScarInputError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ScarInputError("MALFORMED_JSON", str(exc)) from exc
    _depth(value)
    return value


def _object(
    value: Any, name: str, required: set[str], optional: set[str] | None = None
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ScarInputError("INVALID_SHAPE", f"{name} must be an object")
    allowed = required | (optional or set())
    missing = required - value.keys()
    extra = value.keys() - allowed
    if missing:
        raise ScarInputError(
            "MISSING_FIELD", f"{name} missing fields: {sorted(missing)}"
        )
    if extra:
        raise ScarInputError(
            "UNKNOWN_FIELD", f"{name} has unknown fields: {sorted(extra)}"
        )
    return value


def _string(value: Any, name: str, *, nonempty: bool = True) -> str:
    if not isinstance(value, str) or (nonempty and not value):
        raise ScarInputError(
            "INVALID_FIELD", f"{name} must be a {'nonempty ' if nonempty else ''}string"
        )
    return value


def _integer(value: Any, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ScarInputError("INVALID_FIELD", f"{name} must be an integer >= {minimum}")
    return value


def _unique_ids(rows: list[dict[str, Any]], field: str, label: str) -> set[str]:
    ids: set[str] = set()
    for row in rows:
        value = _string(row.get(field), f"{label}.{field}")
        if value in ids:
            raise ScarInputError(
                f"DUPLICATE_{label.upper()}_ID", f"duplicate {label} id: {value}"
            )
        ids.add(value)
    return ids


def validate_envelope(value: Any) -> dict[str, Any]:
    """Validate bounded schema and identifiers; returns the same JSON-compatible mapping."""
    env = _object(
        value,
        "envelope",
        {
            "schema_version",
            "workflow_id",
            "scope",
            "obligations",
            "agents",
            "events",
            "claims",
            "evidence",
            "policy",
        },
    )
    if env["schema_version"] != INPUT_SCHEMA:
        raise ScarInputError("UNSUPPORTED_SCHEMA_VERSION", f"expected {INPUT_SCHEMA}")
    _string(env["workflow_id"], "workflow_id")
    scope = _object(
        env["scope"],
        "scope",
        {
            "repository_id",
            "tree_digest",
            "patch_digest",
            "manifest_digest",
            "epoch",
            "schema_version",
            "verifier_policy_id",
        },
    )
    for name in (
        "repository_id",
        "tree_digest",
        "patch_digest",
        "manifest_digest",
        "verifier_policy_id",
    ):
        _string(scope[name], f"scope.{name}")
    for name in ("tree_digest", "patch_digest", "manifest_digest"):
        digest = scope[name]
        if len(digest) != 64 or any(c not in HEX for c in digest):
            raise ScarInputError(
                "INVALID_DIGEST", f"scope.{name} must be 64 lowercase hex characters"
            )
    _integer(scope["epoch"], "scope.epoch")
    if scope["schema_version"] != 1:
        raise ScarInputError(
            "UNSUPPORTED_SCHEMA_VERSION", "scope.schema_version must be 1"
        )
    lists = ("obligations", "agents", "events", "claims", "evidence")
    for name in lists:
        if not isinstance(env[name], list):
            raise ScarInputError("INVALID_SHAPE", f"{name} must be an array")
        if len(env[name]) > MAX_ROWS:
            raise ScarInputError("ROW_LIMIT", f"{name} exceeds {MAX_ROWS} rows")
    if not 1 <= len(env["obligations"]) <= MAX_OBLIGATIONS:
        raise ScarInputError(
            "OBLIGATION_LIMIT", f"obligations must contain 1..{MAX_OBLIGATIONS} items"
        )
    obligations = []
    for item in env["obligations"]:
        row = _object(
            item,
            "obligation",
            {
                "obligation_id",
                "title",
                "obligation_type",
                "depends_on",
                "applicability",
                "accepted_evidence_classes",
                "verifier_id",
            },
        )
        _string(row["obligation_id"], "obligation_id")
        _string(row["title"], "title")
        _string(row["obligation_type"], "obligation_type")
        _string(row["applicability"], "applicability")
        _string(row["verifier_id"], "verifier_id")
        if not isinstance(row["depends_on"], list) or not isinstance(
            row["accepted_evidence_classes"], list
        ):
            raise ScarInputError(
                "INVALID_FIELD", "obligation dependency/evidence fields must be arrays"
            )
        if (
            len(row["depends_on"]) > MAX_ROWS
            or len(row["accepted_evidence_classes"]) > MAX_ROWS
            or any(
                not isinstance(x, str) or not x
                for x in row["accepted_evidence_classes"]
            )
        ):
            raise ScarInputError(
                "INVALID_FIELD",
                "obligation references must be bounded nonempty strings",
            )
        obligations.append(row)
    obligation_ids = _unique_ids(obligations, "obligation_id", "obligation")
    for row in obligations:
        if any(dep not in obligation_ids for dep in row["depends_on"]):
            raise ScarInputError(
                "UNKNOWN_OBLIGATION", f"{row['obligation_id']} has unknown dependency"
            )
        if row["obligation_id"] in row["depends_on"]:
            raise ScarInputError(
                "DEPENDENCY_CYCLE", "obligation cannot depend on itself"
            )
    agents = []
    for item in env["agents"]:
        row = _object(item, "agent", {"agent_id", "declared_epoch", "state"})
        _string(row["agent_id"], "agent_id")
        _integer(row["declared_epoch"], "agent.declared_epoch")
        _string(row["state"], "agent.state")
        agents.append(row)
    agent_ids = _unique_ids(agents, "agent_id", "agent")
    events = []
    for item in env["events"]:
        row = _object(
            item,
            "event",
            {
                "event_id",
                "agent_id",
                "parent_event_ids",
                "source_epoch",
                "source_tree_digest",
                "claim_ids",
                "delivery",
            },
        )
        _string(row["event_id"], "event_id")
        _string(row["agent_id"], "event.agent_id")
        if row["agent_id"] not in agent_ids:
            raise ScarInputError(
                "UNKNOWN_AGENT", f"unknown event agent {row['agent_id']}"
            )
        if (
            not isinstance(row["parent_event_ids"], list)
            or not isinstance(row["claim_ids"], list)
            or len(row["parent_event_ids"]) > MAX_ROWS
            or len(row["claim_ids"]) > MAX_ROWS
        ):
            raise ScarInputError(
                "INVALID_FIELD", "event parent/claim ids must be bounded arrays"
            )
        _integer(row["source_epoch"], "event.source_epoch")
        _string(row["source_tree_digest"], "event.source_tree_digest")
        _string(row["delivery"], "event.delivery")
        if row["delivery"] not in ("RECEIVED", "IN_FLIGHT"):
            raise ScarInputError(
                "INVALID_FIELD", "event.delivery must be RECEIVED or IN_FLIGHT"
            )
        events.append(row)
    _unique_ids(events, "event_id", "event")
    claims = []
    for item in env["claims"]:
        row = _object(
            item,
            "claim",
            {
                "claim_id",
                "obligation_id",
                "polarity",
                "evidence_ids",
                "asserted_tree_digest",
                "asserted_epoch",
                "verifier_id",
                "event_id",
                "origin_authenticated",
                "provenance",
                "caveats",
            },
        )
        _string(row["claim_id"], "claim_id")
        _string(row["obligation_id"], "claim.obligation_id")
        if row["obligation_id"] not in obligation_ids:
            raise ScarInputError(
                "UNKNOWN_OBLIGATION", f"unknown claim obligation {row['obligation_id']}"
            )
        if row["polarity"] not in ("SUPPORT", "REFUTE"):
            raise ScarInputError(
                "INVALID_FIELD", "claim polarity must be SUPPORT or REFUTE"
            )
        if (
            not isinstance(row["evidence_ids"], list)
            or not isinstance(row["caveats"], list)
            or len(row["evidence_ids"]) > MAX_ROWS
            or len(row["caveats"]) > MAX_ROWS
        ):
            raise ScarInputError(
                "INVALID_FIELD", "claim evidence_ids/caveats must be bounded arrays"
            )
        _string(row["asserted_tree_digest"], "claim.asserted_tree_digest")
        _integer(row["asserted_epoch"], "claim.asserted_epoch")
        _string(row["verifier_id"], "claim.verifier_id")
        _string(row["event_id"], "claim.event_id")
        _string(row["provenance"], "claim.provenance")
        if not isinstance(row["origin_authenticated"], bool):
            raise ScarInputError(
                "INVALID_FIELD", "origin_authenticated must be boolean"
            )
        claims.append(row)
    _unique_ids(claims, "claim_id", "claim")
    evidences = []
    for item in env["evidence"]:
        row = _object(
            item,
            "evidence",
            {
                "evidence_id",
                "path",
                "sha256",
                "evidence_class",
                "source_tree_digest",
                "source_epoch",
                "creator_id",
            },
        )
        for name in (
            "evidence_id",
            "path",
            "sha256",
            "evidence_class",
            "source_tree_digest",
            "creator_id",
        ):
            _string(row[name], f"evidence.{name}")
        _integer(row["source_epoch"], "evidence.source_epoch")
        if len(row["sha256"]) != 64 or any(c not in HEX for c in row["sha256"]):
            raise ScarInputError(
                "INVALID_DIGEST", "evidence.sha256 must be 64 lowercase hex characters"
            )
        evidences.append(row)
    evidence_ids = _unique_ids(evidences, "evidence_id", "evidence")
    for claim in claims:
        if any(eid not in evidence_ids for eid in claim["evidence_ids"]):
            # Missing references are reportable evidence failures, not parser crashes.
            continue
    policy = _object(
        env["policy"],
        "policy",
        {
            "policy_id",
            "allowed_queries",
            "timeout_allowed",
            "advisory_when_complete",
            "host_authorization_required",
            "max_states",
        },
    )
    _string(policy["policy_id"], "policy.policy_id")
    _string(policy["advisory_when_complete"], "policy.advisory_when_complete")
    if (
        not isinstance(policy["allowed_queries"], list)
        or len(policy["allowed_queries"]) > MAX_ROWS
        or not isinstance(policy["timeout_allowed"], bool)
        or policy["host_authorization_required"] is not True
    ):
        raise ScarInputError(
            "INVALID_POLICY", "policy query/timeout/authorization shape invalid"
        )
    _integer(policy["max_states"], "policy.max_states", 1)
    if policy["max_states"] > MAX_STATES:
        raise ScarInputError("STATE_CAP", "policy max_states exceeds hard cap")
    minimum_states = 2 ** len(obligations)
    if policy["max_states"] < minimum_states:
        raise ScarInputError(
            "STATE_CAP",
            f"policy max_states must be at least {minimum_states} for this obligation count",
        )
    queries = []
    for item in policy["allowed_queries"]:
        row = _object(
            item, "query", {"query_id", "obligation_id", "cost", "allowed_outcomes"}
        )
        _string(row["query_id"], "query.query_id")
        _string(row["obligation_id"], "query.obligation_id")
        _integer(row["cost"], "query.cost")
        if row["obligation_id"] not in obligation_ids:
            raise ScarInputError(
                "UNKNOWN_OBLIGATION",
                f"query refers to unknown obligation {row['obligation_id']}",
            )
        if not isinstance(row["allowed_outcomes"], list) or any(
            x not in ("SUPPORT", "REFUTE", "UNKNOWN", "TIMEOUT")
            for x in row["allowed_outcomes"]
        ):
            raise ScarInputError("INVALID_POLICY", "invalid query outcome")
        queries.append(row)
    _unique_ids(queries, "query_id", "query")
    _check_dependency_dag(obligations)
    _check_event_cycles(events)
    return env


def _check_dependency_dag(obligations: list[dict[str, Any]]) -> None:
    graph = {o["obligation_id"]: o["depends_on"] for o in obligations}
    visiting = set()
    done = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise ScarInputError("DEPENDENCY_CYCLE", f"dependency cycle at {node}")
        if node in done:
            return
        visiting.add(node)
        for dep in graph[node]:
            visit(dep)
        visiting.remove(node)
        done.add(node)

    for node in graph:
        visit(node)


def _check_event_cycles(events: list[dict[str, Any]]) -> None:
    graph = {
        e["event_id"]: [
            p for p in e["parent_event_ids"] if p in {x["event_id"] for x in events}
        ]
        for e in events
    }
    visiting = set()
    done = set()

    def visit(node: str) -> None:
        if node in visiting:
            raise ScarInputError("EVENT_CYCLE", f"event cycle at {node}")
        if node in done:
            return
        visiting.add(node)
        for parent in graph[node]:
            visit(parent)
        visiting.remove(node)
        done.add(node)

    for node in graph:
        visit(node)


@dataclass(frozen=True)
class RecoveryAssessment:
    schema_version: str
    workflow_id: str
    status: str
    outcome: str
    scope: Mapping[str, Any]
    obligation_states: tuple[Mapping[str, Any], ...]
    supported_completed_obligations: tuple[str, ...]
    unresolved_obligations: tuple[str, ...]
    conflicts: tuple[Mapping[str, Any], ...]
    stale_evidence: tuple[Mapping[str, Any], ...]
    missing_causal_parents: tuple[Mapping[str, Any], ...]
    invalid_or_unverified_claims: tuple[Mapping[str, Any], ...]
    feasible_state_count: int
    feasible_state_cap: int
    feasible_states: tuple[Mapping[str, bool], ...]
    possible_action_classes: tuple[str, ...]
    recommendations: tuple[Mapping[str, Any], ...]
    abstain_reason: str | None
    evidence_refs: tuple[str, ...]
    policy_ref: str
    assumptions: tuple[str, ...]
    host_authorization_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "workflow_id": self.workflow_id,
            "status": self.status,
            "outcome": self.outcome,
            "scope": dict(self.scope),
            "obligation_states": [dict(x) for x in self.obligation_states],
            "supported_completed_obligations": list(
                self.supported_completed_obligations
            ),
            "unresolved_obligations": list(self.unresolved_obligations),
            "conflicts": [dict(x) for x in self.conflicts],
            "stale_evidence": [dict(x) for x in self.stale_evidence],
            "missing_causal_parents": [dict(x) for x in self.missing_causal_parents],
            "invalid_or_unverified_claims": [
                dict(x) for x in self.invalid_or_unverified_claims
            ],
            "feasible_state_count": self.feasible_state_count,
            "feasible_state_cap": self.feasible_state_cap,
            "feasible_states": [dict(x) for x in self.feasible_states],
            "possible_action_classes": list(self.possible_action_classes),
            "recommendations": [dict(x) for x in self.recommendations],
            "abstain_reason": self.abstain_reason,
            "evidence_refs": list(self.evidence_refs),
            "policy_ref": self.policy_ref,
            "assumptions": list(self.assumptions),
            "host_authorization_required": self.host_authorization_required,
        }


def validate_assessment_roundtrip(value: Any) -> dict[str, Any]:
    """Conservative shape/version check for JSON report round-trip tests and consumers."""
    row = _object(
        value,
        "assessment",
        {
            "schema_version",
            "workflow_id",
            "status",
            "outcome",
            "scope",
            "obligation_states",
            "supported_completed_obligations",
            "unresolved_obligations",
            "conflicts",
            "stale_evidence",
            "missing_causal_parents",
            "invalid_or_unverified_claims",
            "feasible_state_count",
            "feasible_state_cap",
            "feasible_states",
            "possible_action_classes",
            "recommendations",
            "abstain_reason",
            "evidence_refs",
            "policy_ref",
            "assumptions",
            "host_authorization_required",
        },
    )
    if row["schema_version"] != OUTPUT_SCHEMA:
        raise ScarInputError(
            "UNSUPPORTED_ASSESSMENT_VERSION", "unsupported assessment schema"
        )
    if row["host_authorization_required"] is not True:
        raise ScarInputError(
            "INVALID_ASSESSMENT", "host authorization flag must remain true"
        )
    return row
