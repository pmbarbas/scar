"""Offline CLI facade; all inspect/explain/demo behavior remains in accepted core."""
from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="scar-kit", description="Offline SCAR Evidence Inspector and Recovery Test Kit")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("version", help="show local toolkit and accepted core versions")
    commands.add_parser("test", help="run deterministic installed-package recovery smoke checks")
    commands.add_parser("demo", help="run accepted core bundled recovery example")
    inspect = commands.add_parser("inspect", help="inspect a local envelope using the accepted digest-only CLI verifier")
    inspect.add_argument("--input", required=True)
    inspect.add_argument("--root", required=True)
    inspect.add_argument("--format", choices=("json", "text"), default="text")
    explain = commands.add_parser("explain", help="explain an assessment from a local envelope")
    explain.add_argument("--input", required=True)
    explain.add_argument("--root", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "version":
            from importlib.metadata import PackageNotFoundError, version
            from . import __version__
            try:
                core_version = version("scar-research-toolkit")
            except PackageNotFoundError:
                print("SCAR Research Toolkit installation metadata is unavailable.", file=sys.stderr)
                return 2
            print(json.dumps({"toolkit": __version__, "core_api": core_version}, sort_keys=True))
            return 0
        if args.command == "test":
            from .kit import run_kit
            print(json.dumps(run_kit(), indent=2, sort_keys=True))
            return 0
        from scar_core.cli import main as core_main
        if args.command == "demo":
            return core_main(["demo"])
        if args.command == "inspect":
            return core_main(["inspect", "--input", args.input, "--root", args.root, "--format", args.format])
        if args.command == "explain":
            return core_main(["explain", "--input", args.input, "--root", args.root])
        return 2
    except (ImportError, OSError, ValueError) as exc:
        print("SCAR Kit error: request could not be processed safely.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
