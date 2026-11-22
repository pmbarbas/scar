#!/usr/bin/env python3
"""Fail on obvious secrets, personal paths, or unexpected binary payloads."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_TEXT = ("/" + "Users/", "/" + "private/" + "tmp/")
PATTERNS = [
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"(?i)(?:api[_-]?key|secret|password)\s*[:=]\s*[A-Za-z0-9_./+=-]{12,}"),
    re.compile(rb"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
]
SKIP_PARTS = {".git", ".build", ".venv", "__pycache__", "dist", "build", ".test-tmp"}


def main() -> None:
    issues = []
    scanned = 0
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        if any(part in SKIP_PARTS for part in rel.parts):
            continue
        if path.is_symlink():
            issues.append(f"symlink: {rel}")
            continue
        if not path.is_file():
            continue
        data = path.read_bytes()
        scanned += 1
        if b"\x00" in data:
            issues.append(f"binary/NUL payload: {rel}")
        for token in FORBIDDEN_TEXT:
            if token.encode() in data:
                issues.append(f"excluded identifier/path {token!r}: {rel}")
        for pattern in PATTERNS:
            if pattern.search(data):
                issues.append(f"secret/contact-pattern candidate: {rel}")
    if issues:
        raise SystemExit("public-scope scan failed:\n" + "\n".join(issues))
    print(f"PASS: scanned {scanned} public source files; no listed personal paths, secrets, symlinks or NUL binaries")


if __name__ == "__main__":
    main()
