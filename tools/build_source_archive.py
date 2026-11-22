#!/usr/bin/env python3
"""Create a deterministic clean-room source ZIP and its SHA-256 manifest."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import stat
import zipfile


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "PUBLIC_SCOPE_MANIFEST.sha256"
DEFAULT_ARCHIVE = ROOT / ".build" / "SCAR_RESEARCH_PUBLIC_REPOSITORY.zip"
SKIP_PARTS = {".git", ".build", ".venv", "__pycache__", "dist", "build", ".test-tmp"}


def included_files() -> list[Path]:
    files = []
    for path in ROOT.rglob("*"):
        if any(part in SKIP_PARTS for part in path.relative_to(ROOT).parts):
            continue
        if path.is_symlink():
            raise SystemExit(f"symlink not permitted in source tree: {path.relative_to(ROOT)}")
        if path.is_file() and path != MANIFEST:
            files.append(path)
    return sorted(files, key=lambda p: p.relative_to(ROOT).as_posix())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_ARCHIVE)
    args = parser.parse_args()
    files = included_files()
    manifest = "".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(ROOT).as_posix()}\n" for p in files)
    MANIFEST.write_text(manifest, encoding="utf-8")
    files.append(MANIFEST)
    files.sort(key=lambda p: p.relative_to(ROOT).as_posix())
    out = args.output.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in files:
            name = path.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            zf.writestr(info, path.read_bytes())
    print(f"source_files={len(files)} archive={out} sha256={hashlib.sha256(out.read_bytes()).hexdigest()}")


if __name__ == "__main__":
    main()
