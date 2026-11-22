"""Bounded, transitive causal-cut validation for a validated event DAG."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any
from .contracts import ScarInputError


@dataclass(frozen=True)
class CausalReport:
    missing_parents: tuple[dict[str, Any], ...]
    incomplete_events: tuple[str, ...]
    claim_event_errors: tuple[dict[str, Any], ...]
    ordered_event_ids: tuple[str, ...]
    incomplete_event_causes: tuple[dict[str, Any], ...]


def _cause_key(cause: dict[str, Any]) -> tuple[Any, ...]:
    path = tuple(cause["causal_path"])
    return (
        len(path),
        path,
        cause["root_reason_code"],
        cause["root_event_id"],
        cause.get("claim_id", ""),
    )


def analyze_causality(envelope: dict[str, Any]) -> CausalReport:
    """Compute a canonical root-cause path for every transitively incomplete event.

    The validated envelope caps events and parent references at 256. Kahn's
    algorithm visits each event once; propagation visits each declared edge
    once. The event DAG is acyclic, so this pass terminates in O(V + E log V)
    with deterministic lexical ordering. Only one canonical path per event is
    retained; all direct missing-parent and binding diagnostics are preserved.
    """
    events = {event["event_id"]: event for event in envelope["events"]}
    claims = {claim["claim_id"]: claim for claim in envelope["claims"]}
    direct: dict[str, list[dict[str, Any]]] = {eid: [] for eid in events}
    missing: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    def add_error(row: dict[str, Any], affected_event: str | None) -> None:
        errors.append(row)
        if affected_event in direct:
            errorsource = row.get("reason_code", "CLAIM_EVENT_BINDING_INVALID")
            direct[affected_event].append(
                {
                    "root_event_id": affected_event,
                    "root_reason_code": errorsource,
                    "causal_path": [affected_event],
                    "claim_id": row.get("claim_id"),
                }
            )

    scope = envelope["scope"]
    for eid, event in events.items():
        if event["delivery"] != "RECEIVED":
            direct[eid].append(
                {
                    "root_event_id": eid,
                    "root_reason_code": "EVENT_NOT_RECEIVED",
                    "causal_path": [eid],
                }
            )
        if (
            event["source_epoch"] != scope["epoch"]
            or event["source_tree_digest"] != scope["tree_digest"]
        ):
            direct[eid].append(
                {
                    "root_event_id": eid,
                    "root_reason_code": "EVENT_SOURCE_SCOPE_MISMATCH",
                    "causal_path": [eid],
                }
            )
        link_counts: dict[str, int] = {}
        for cid in event["claim_ids"]:
            link_counts[cid] = link_counts.get(cid, 0) + 1
        for cid, count in sorted(link_counts.items()):
            if count > 1:
                add_error(
                    {
                        "claim_id": cid,
                        "event_id": eid,
                        "reason_code": "DUPLICATE_EVENT_CLAIM_REFERENCE",
                    },
                    eid,
                )
            claim = claims.get(cid)
            if claim is None:
                add_error(
                    {
                        "claim_id": cid,
                        "event_id": eid,
                        "reason_code": "EVENT_CLAIM_REFERENCE_MISSING",
                    },
                    eid,
                )
            elif claim["event_id"] != eid:
                add_error(
                    {
                        "claim_id": cid,
                        "event_id": eid,
                        "claim_event_id": claim["event_id"],
                        "reason_code": "EVENT_CLAIM_LINK_MISMATCH",
                    },
                    eid,
                )
                if claim["event_id"] in events:
                    add_error(
                        {
                            "claim_id": cid,
                            "event_id": claim["event_id"],
                            "listed_by_event_id": eid,
                            "reason_code": "EVENT_CLAIM_LINK_MISMATCH",
                        },
                        claim["event_id"],
                    )
        for parent in event["parent_event_ids"]:
            if parent not in events:
                row = {
                    "event_id": eid,
                    "missing_parent_event_id": parent,
                    "reason_code": "MISSING_CAUSAL_PARENT",
                }
                missing.append(row)
                direct[eid].append(
                    {
                        "root_event_id": parent,
                        "root_reason_code": "MISSING_CAUSAL_PARENT",
                        "causal_path": [eid, parent],
                    }
                )

    for claim in envelope["claims"]:
        cid = claim["claim_id"]
        event = events.get(claim["event_id"])
        if event is None:
            add_error(
                {
                    "claim_id": cid,
                    "event_id": claim["event_id"],
                    "reason_code": "CLAIM_EVENT_MISSING",
                },
                None,
            )
            continue
        if cid not in event["claim_ids"]:
            add_error(
                {
                    "claim_id": cid,
                    "event_id": event["event_id"],
                    "reason_code": "CLAIM_EVENT_LINK_MISSING",
                },
                event["event_id"],
            )
        if (
            event["source_epoch"] != claim["asserted_epoch"]
            or event["source_tree_digest"] != claim["asserted_tree_digest"]
        ):
            add_error(
                {
                    "claim_id": cid,
                    "event_id": event["event_id"],
                    "reason_code": "CLAIM_EVENT_SCOPE_MISMATCH",
                },
                event["event_id"],
            )

    # Stable Kahn ordering over present parent references; absent parents have
    # already been recorded as direct causal faults rather than graph vertices.
    indegree = {eid: 0 for eid in events}
    children: dict[str, list[str]] = {eid: [] for eid in events}
    for eid, event in events.items():
        for parent in event["parent_event_ids"]:
            if parent in events:
                indegree[eid] += 1
                children[parent].append(eid)
    ready = sorted(eid for eid, count in indegree.items() if count == 0)
    ordered = []
    while ready:
        eid = ready.pop(0)
        ordered.append(eid)
        for child in sorted(children[eid]):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort()
    if len(ordered) != len(events):
        # Normally caught by validate_envelope; keep the public helper safe too.
        raise ScarInputError("EVENT_CYCLE", "event graph is not acyclic")

    best: dict[str, dict[str, Any]] = {}
    for eid in ordered:
        candidates = list(direct[eid])
        event = events[eid]
        for parent in event["parent_event_ids"]:
            if parent in best:
                inherited = dict(best[parent])
                inherited["causal_path"] = [eid, *best[parent]["causal_path"]]
                candidates.append(inherited)
        if candidates:
            best[eid] = min(candidates, key=_cause_key)

    incomplete = tuple(eid for eid in ordered if eid in best)
    path_diagnostics = tuple(
        {"event_id": eid, **best[eid]} for eid in sorted(incomplete)
    )
    missing_sorted = tuple(
        sorted(
            missing, key=lambda row: (row["event_id"], row["missing_parent_event_id"])
        )
    )
    errors_sorted = tuple(
        sorted(
            errors,
            key=lambda row: (
                row.get("event_id", ""),
                row.get("claim_id", ""),
                row["reason_code"],
            ),
        )
    )
    return CausalReport(
        missing_sorted, incomplete, errors_sorted, tuple(ordered), path_diagnostics
    )


def claim_has_complete_cut(claim: dict[str, Any], causal: CausalReport) -> bool:
    return claim["event_id"] not in set(causal.incomplete_events) and not any(
        row["claim_id"] == claim["claim_id"] for row in causal.claim_event_errors
    )
