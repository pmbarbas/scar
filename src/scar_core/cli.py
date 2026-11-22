"""Offline SCAR command line. No network, shell execution, or input-directed imports."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence
from .contracts import ScarInputError, parse_json_bytes, validate_envelope
from .demo import run_demo
from .recovery import inspect_evidence
from .report import render_text
from .secureio import read_bounded_path
from .contracts import MAX_INPUT_BYTES
from .verify import DigestOnlyVerifier


def _load(path: Path) -> dict[str, Any]:
    raw = read_bounded_path(path, MAX_INPUT_BYTES, "INPUT_TOO_LARGE")
    return validate_envelope(parse_json_bytes(raw))


_IDENTITY_KEYS = {
    "workflow_id", "repository_id", "tree_digest", "patch_digest", "manifest_digest",
    "verifier_policy_id", "policy_id", "policy_ref", "obligation_id", "claim_id",
    "evidence_id", "agent_id", "event_id", "query_id", "verifier_id", "creator_id",
    "missing_parent_event_id", "root_event_id", "listed_by_event_id", "claim_event_id",
    "support_claim_ids", "refute_claim_ids", "evidence_refs", "verifier_ids",
}


def _redact_identities(value: Any) -> Any:
    """Replace identifiers in CLI output with stable local aliases."""
    originals: list[str] = []

    def collect(node: Any, key: str = "") -> None:
        if isinstance(node, dict):
            for child_key, child in node.items():
                collect(child, child_key)
        elif isinstance(node, (list, tuple)):
            for child in node:
                collect(child, key)
        elif isinstance(node, str) and key in _IDENTITY_KEYS and node not in originals:
            originals.append(node)

    collect(value)
    aliases = {original: f"item-{index:03d}" for index, original in enumerate(originals, 1)}

    def replace(node: Any, key: str = "") -> Any:
        if isinstance(node, dict):
            return {k: replace(v, k) for k, v in node.items()}
        if isinstance(node, (list, tuple)):
            return [replace(v, key) for v in node]
        if isinstance(node, str) and node in aliases:
            return aliases[node]
        return node

    return replace(value)


def _assessment(args: argparse.Namespace) -> dict[str, Any]:
    env = _load(Path(args.input))
    result = inspect_evidence(
        env, Path(args.root), DigestOnlyVerifier(), env["policy"]
    ).to_dict()
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="scar",
        description="Offline evidence-aware workflow recovery inspector (advisory only)",
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("demo", help="run the bundled offline H8/H9 recovery demonstration")
    inspect = sub.add_parser(
        "inspect", help="inspect a local evidence envelope without writing"
    )
    inspect.add_argument("--input", required=True)
    inspect.add_argument("--root", required=True)
    inspect.add_argument("--format", choices=("json", "text"), default="text")
    explain = sub.add_parser("explain", help="explain the local evidence assessment")
    explain.add_argument("--input", required=True)
    explain.add_argument("--root", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    try:
        if args.command == "demo":
            result, story = run_demo()
            print(story)
            print(json.dumps(result, sort_keys=True, indent=2))
            return 0
        result = _assessment(args)
        safe_result = _redact_identities(result)
        print(
            json.dumps(safe_result, sort_keys=True, indent=2)
            if getattr(args, "format", None) == "json"
            else render_text(safe_result)
        )
        return 0
    except ScarInputError as exc:
        error = {
            "status": "INVALID_INPUT",
            "reason_code": exc.code,
            "message": "Input was rejected by the SCAR safety or schema checks.",
            "host_authorization_required": True,
        }
        print(
            json.dumps(error, sort_keys=True)
            if getattr(args, "format", None) == "json"
            else f"SCAR INVALID_INPUT [{exc.code}]: {exc.message}",
            file=sys.stderr,
        )
        return 2
    except (OSError, ValueError):
        print("SCAR ERROR: input could not be processed safely.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
