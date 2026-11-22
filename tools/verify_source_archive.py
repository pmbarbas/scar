#!/usr/bin/env python3
"""Verify safe paths, exact manifest coverage, ZIP CRC and file hashes."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path, PurePosixPath
import stat
import zipfile


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "PUBLIC_SCOPE_MANIFEST.sha256"
DEFAULT_ARCHIVE = ROOT / ".build" / "SCAR_RESEARCH_PUBLIC_REPOSITORY.zip"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", nargs="?", type=Path, default=DEFAULT_ARCHIVE)
    args = parser.parse_args()
    rows = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        rows[name] = digest
    expected = set(rows) | {"PUBLIC_SCOPE_MANIFEST.sha256"}
    with zipfile.ZipFile(args.archive) as zf:
        infos = zf.infolist()
        names = [x.filename for x in infos]
        if len(names) != len(set(names)) or set(names) != expected:
            raise SystemExit("source archive member set differs from manifest")
        for info in infos:
            name = PurePosixPath(info.filename)
            if name.is_absolute() or ".." in name.parts or "\\" in info.filename:
                raise SystemExit("unsafe source archive member path")
            if stat.S_ISLNK(info.external_attr >> 16):
                raise SystemExit("symlink source archive member is forbidden")
        if zf.testzip():
            raise SystemExit("source archive CRC failure")
        if zf.read("PUBLIC_SCOPE_MANIFEST.sha256") != MANIFEST.read_bytes():
            raise SystemExit("embedded manifest differs from workspace manifest")
        for name, digest in rows.items():
            if hashlib.sha256(zf.read(name)).hexdigest() != digest:
                raise SystemExit(f"source archive hash mismatch: {name}")
    print(f"PASS: source files={len(rows)}; safe paths, exact coverage, CRC, manifest hashes")


if __name__ == "__main__":
    main()
