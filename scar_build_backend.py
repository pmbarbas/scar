"""Minimal deterministic PEP 517 backend using Python's standard library only."""
from __future__ import annotations

import base64
import csv
import gzip
import hashlib
import io
from pathlib import Path
import tarfile
import zipfile

NAME = "scar-research-toolkit"
VERSION = "0.2.0"
DIST = "scar_research_toolkit-0.2.0"
FIXED_TIME = (1980, 1, 1, 0, 0, 0)
SDIST_TIME = 315532800
SKIP_PARTS = {".git", ".build", ".venv", "__pycache__", "dist", "build", ".test-tmp"}


def _root() -> Path:
    return Path(__file__).resolve().parent


def _metadata() -> bytes:
    return (
        "Metadata-Version: 2.4\n"
        f"Name: {NAME}\n"
        f"Version: {VERSION}\n"
        "Summary: Experimental offline toolkit for inspecting structured agent-workflow evidence\n"
        "Requires-Python: >=3.11\n"
        "License-Expression: Apache-2.0\n"
        "License-File: LICENSE\n"
        "License-File: NOTICE\n"
        "\n"
    ).encode("utf-8")


def _wheel_members() -> list[tuple[str, bytes]]:
    root = _root()
    members: list[tuple[str, bytes]] = []
    for package in ("scar_core", "scar_toolkit"):
        base = root / "src" / package
        for path in sorted(base.rglob("*")):
            if path.is_symlink():
                raise RuntimeError("symlink is forbidden in wheel input")
            if path.is_file() and path.suffix in {".py", ".json"}:
                members.append((path.relative_to(root / "src").as_posix(), path.read_bytes()))
    return members


def _record_row(name: str, data: bytes) -> tuple[str, str, str]:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
    return name, f"sha256={digest}", str(len(data))


def _write_wheel(output: Path) -> str:
    dist_info = f"{DIST}.dist-info"
    metadata = _metadata()
    wheel = (
        "Wheel-Version: 1.0\n"
        "Generator: scar-build-backend\n"
        "Root-Is-Purelib: true\n"
        "Tag: py3-none-any\n\n"
    ).encode()
    entry_points = (
        "[console_scripts]\n"
        "scar = scar_core.cli:main\n"
        "scar-kit = scar_toolkit.cli:main\n"
    ).encode()
    members = _wheel_members() + [
        (f"{dist_info}/METADATA", metadata),
        (f"{dist_info}/licenses/LICENSE", (_root() / "LICENSE").read_bytes()),
        (f"{dist_info}/licenses/NOTICE", (_root() / "NOTICE").read_bytes()),
        (f"{dist_info}/WHEEL", wheel),
        (f"{dist_info}/entry_points.txt", entry_points),
    ]
    record_name = f"{dist_info}/RECORD"
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    for name, data in members:
        writer.writerow(_record_row(name, data))
    writer.writerow((record_name, "", ""))
    members.append((record_name, stream.getvalue().encode()))
    output.mkdir(parents=True, exist_ok=True)
    destination = output / f"{DIST}-py3-none-any.whl"
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(members):
            info = zipfile.ZipInfo(name, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return destination.name


def _source_members() -> list[tuple[str, bytes]]:
    root = _root()
    members = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(part in SKIP_PARTS for part in rel.parts) or path == root / "PUBLIC_SCOPE_MANIFEST.sha256":
            continue
        if path.is_symlink():
            raise RuntimeError("symlink is forbidden in source distribution input")
        if path.is_file():
            members.append((rel.as_posix(), path.read_bytes()))
    return members


def _write_sdist(output: Path) -> str:
    output.mkdir(parents=True, exist_ok=True)
    destination = output / f"{DIST}.tar.gz"
    with destination.open("wb") as raw:
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                for name, data in _source_members():
                    info = tarfile.TarInfo(f"{DIST}/{name}")
                    info.size = len(data)
                    info.mode = 0o644
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    info.mtime = SDIST_TIME
                    archive.addfile(info, io.BytesIO(data))
                pkg_info = _metadata()
                info = tarfile.TarInfo(f"{DIST}/PKG-INFO")
                info.size = len(pkg_info)
                info.mode = 0o644
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mtime = SDIST_TIME
                archive.addfile(info, io.BytesIO(pkg_info))
    return destination.name


def get_requires_for_build_wheel(config_settings=None):
    return []


def get_requires_for_build_sdist(config_settings=None):
    return []


def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None):
    target = Path(metadata_directory) / f"{DIST}.dist-info"
    target.mkdir(parents=True, exist_ok=True)
    (target / "METADATA").write_bytes(_metadata())
    return target.name


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    return _write_wheel(Path(wheel_directory))


def build_sdist(sdist_directory, config_settings=None):
    return _write_sdist(Path(sdist_directory))
