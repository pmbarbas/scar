"""Fail-closed, descriptor-anchored POSIX file access for untrusted inputs."""
from __future__ import annotations

import errno
import os
import stat

from .contracts import ScarInputError

_OPEN_SUPPORTS_DIR_FD = os.open in os.supports_dir_fd


def _require_secure_posix() -> None:
    if (
        os.name != "posix"
        or not hasattr(os, "O_NOFOLLOW")
        or not hasattr(os, "O_DIRECTORY")
        or not _OPEN_SUPPORTS_DIR_FD
    ):
        raise ScarInputError("SECURE_IO_UNSUPPORTED", "secure POSIX file access is unavailable")


def _directory_fd(path: str | os.PathLike[str], code: str) -> int:
    """Open an absolute directory component-by-component without following links."""
    _require_secure_posix()
    raw = os.fspath(path)
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise ScarInputError("UNSAFE_INPUT_PATH", "input path is invalid")
    if "\\" in raw:
        raise ScarInputError("UNSAFE_INPUT_PATH", "input path is invalid")
    raw_parts = [] if raw == "/" else raw.split("/")
    if raw.startswith("/") and raw != "/":
        raw_parts = raw_parts[1:]
    if any(part in ("", ".", "..") for part in raw_parts):
        raise ScarInputError("UNSAFE_INPUT_PATH", "input path is invalid")
    absolute = raw if raw.startswith("/") else os.path.join(os.getcwd(), raw)
    pieces = absolute.split("/")[1:]
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    current = os.open("/", flags)
    try:
        for part in pieces:
            if not part or part in (".", ".."):
                raise ScarInputError("UNSAFE_INPUT_PATH", "input path is invalid")
            nxt = os.open(part, flags, dir_fd=current)
            os.close(current)
            current = nxt
        return current
    except ScarInputError:
        os.close(current)
        raise
    except (OSError, ValueError, TypeError) as exc:
        os.close(current)
        raise ScarInputError(code, "directory could not be safely opened") from exc


def open_root(path: str | os.PathLike[str]) -> int:
    """Pin the host-selected evidence root; root and ancestors must not be symlinks."""
    return _directory_fd(path, "EVIDENCE_ROOT_INVALID")


def open_relative_regular(root_fd: int, relative: str) -> int:
    """Open a regular file beneath a pinned root using no-follow dir-fd traversal."""
    _require_secure_posix()
    if (
        not isinstance(relative, str)
        or not relative
        or len(relative) > 512
        or relative.startswith("/")
        or "\\" in relative
        or "\x00" in relative
    ):
        raise ScarInputError("UNSAFE_EVIDENCE_PATH", "evidence path is invalid")
    pieces = relative.split("/")
    if any(part in ("", ".", "..") for part in pieces):
        raise ScarInputError("UNSAFE_EVIDENCE_PATH", "evidence path is invalid")
    current = os.dup(root_fd)
    dir_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
    fd: int | None = None
    transferred = False
    try:
        for part in pieces[:-1]:
            nxt = os.open(part, dir_flags, dir_fd=current)
            os.close(current)
            current = nxt
        fd = os.open(pieces[-1], file_flags, dir_fd=current)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode):
            os.close(fd)
            fd = None
            raise ScarInputError("EVIDENCE_NOT_REGULAR_FILE", "evidence must be a regular file")
        transferred = True
        return fd
    except ScarInputError:
        raise
    except (OSError, ValueError, TypeError) as exc:
        if isinstance(exc, FileNotFoundError):
            code = "EVIDENCE_FILE_MISSING"
        elif isinstance(exc, PermissionError):
            code = "EVIDENCE_OPEN_DENIED"
        elif isinstance(exc, OSError) and exc.errno == errno.ELOOP:
            code = "SYMLINK_EVIDENCE_PATH"
        elif isinstance(exc, OSError) and exc.errno == errno.ENOTDIR:
            code = "EVIDENCE_PATH_INVALID"
        else:
            code = "EVIDENCE_OPEN_FAILED"
        raise ScarInputError(code, "evidence could not be safely opened") from exc
    finally:
        if fd is not None and not transferred:
            os.close(fd)
        os.close(current)


def read_bounded_fd(fd: int, limit: int, too_large_code: str) -> bytes:
    """Read at most limit+1 bytes from an already-open descriptor."""
    if limit < 0:
        raise ValueError("limit must be nonnegative")
    chunks = []
    remaining = limit + 1
    try:
        while remaining:
            block = os.read(fd, min(65_536, remaining))
            if not block:
                break
            chunks.append(block)
            remaining -= len(block)
    except OSError as exc:
        raise ScarInputError("INPUT_READ_FAILED", "input could not be read safely") from exc
    data = b"".join(chunks)
    if len(data) > limit:
        raise ScarInputError(too_large_code, "input exceeds the configured size limit")
    return data


def read_bounded_path(path: str | os.PathLike[str], limit: int, too_large_code: str) -> bytes:
    """Safely open an explicit host-selected input file and perform a bounded read."""
    raw = os.fspath(path)
    if not isinstance(raw, str) or not raw or "\x00" in raw:
        raise ScarInputError("UNSAFE_INPUT_PATH", "input path is invalid")
    if "\\" in raw:
        raise ScarInputError("UNSAFE_INPUT_PATH", "input path is invalid")
    raw_parts = [] if raw == "/" else raw.split("/")
    if raw.startswith("/") and raw != "/":
        raw_parts = raw_parts[1:]
    if any(part in ("", ".", "..") for part in raw_parts):
        raise ScarInputError("UNSAFE_INPUT_PATH", "input path is invalid")
    absolute = raw if raw.startswith("/") else os.path.join(os.getcwd(), raw)
    parent, leaf = os.path.split(absolute)
    if not leaf or leaf in (".", ".."):
        raise ScarInputError("UNSAFE_INPUT_PATH", "input path is invalid")
    parent_fd = _directory_fd(parent, "INPUT_OPEN_FAILED")
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(leaf, flags, dir_fd=parent_fd)
    except (OSError, ValueError, TypeError) as exc:
        raise ScarInputError("INPUT_OPEN_FAILED", "input could not be safely opened") from exc
    finally:
        os.close(parent_fd)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ScarInputError("INPUT_NOT_REGULAR_FILE", "input must be a regular file")
        return read_bounded_fd(fd, limit, too_large_code)
    finally:
        os.close(fd)
