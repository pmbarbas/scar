from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from scar_core.cli import _load, _redact_identities, main
from scar_core.contracts import MAX_DEPTH, MAX_INPUT_BYTES, ScarInputError, parse_json_bytes, validate_envelope
from scar_core.demo import _DATA
from scar_core.recovery import _enumerate_states
from scar_core.secureio import open_relative_regular, open_root, read_bounded_fd, read_bounded_path
from scar_core.verify import MAX_EVIDENCE_BYTES, load_evidence


def _record() -> bytes:
    return json.dumps({
        "schema": "scar.fixture.evidence.v1", "evidence_id": "e1", "obligation_id": "o1",
        "source_epoch": 1, "source_tree_digest": "a" * 64, "observed": True, "test_id": "fixture",
    }, sort_keys=True, separators=(",", ":")).encode()


def _reference(path: str, raw: bytes) -> dict:
    return {"evidence_id": "e1", "obligation_id": "o1", "path": path,
            "sha256": hashlib.sha256(raw).hexdigest(), "source_epoch": 1,
            "source_tree_digest": "a" * 64}


class SecureReadTests(unittest.TestCase):
    def setUp(self) -> None:
        scratch = Path(__file__).resolve().parents[1] / ".test-tmp"
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.base = Path(self.temp.name)
        self.root = self.base / "root"
        self.root.mkdir()

    def tearDown(self) -> None:
        location = Path(self.temp.name)
        self.temp.cleanup()
        self.assertFalse(location.exists(), "temporary attack fixture was not cleaned")

    def test_envelope_read_boundaries_and_large_sparse_file(self) -> None:
        exact = self.base / "exact.json"
        exact.write_bytes(b" " * MAX_INPUT_BYTES)
        observed = 0
        original = os.read
        def count_exact(fd: int, amount: int) -> bytes:
            nonlocal observed
            block = original(fd, amount)
            observed += len(block)
            return block
        with patch("scar_core.secureio.os.read", count_exact):
            exact_bytes = read_bounded_path(exact, MAX_INPUT_BYTES, "INPUT_TOO_LARGE")
        self.assertEqual(len(exact_bytes), MAX_INPUT_BYTES)
        self.assertEqual(observed, MAX_INPUT_BYTES)
        plus = self.base / "plus.json"
        plus.write_bytes(b" " * (MAX_INPUT_BYTES + 1))
        observed = 0
        def count(fd: int, amount: int) -> bytes:
            nonlocal observed
            block = original(fd, amount)
            observed += len(block)
            return block
        with patch("scar_core.secureio.os.read", count), self.assertRaises(ScarInputError) as cm:
            read_bounded_path(plus, MAX_INPUT_BYTES, "INPUT_TOO_LARGE")
        self.assertEqual(cm.exception.code, "INPUT_TOO_LARGE")
        self.assertEqual(observed, MAX_INPUT_BYTES + 1)
        sparse = self.base / "sparse.bin"
        with sparse.open("wb") as handle:
            handle.truncate(32 * 1024 * 1024)
        observed = 0
        with patch("scar_core.secureio.os.read", count), self.assertRaises(ScarInputError):
            read_bounded_path(sparse, MAX_INPUT_BYTES, "INPUT_TOO_LARGE")
        self.assertEqual(observed, MAX_INPUT_BYTES + 1)

    def test_evidence_read_boundaries_and_large_sparse_file(self) -> None:
        valid = _record()
        exact = valid + b" " * (MAX_EVIDENCE_BYTES - len(valid))
        (self.root / "exact.json").write_bytes(exact)
        self.assertEqual(load_evidence(self.root, _reference("exact.json", exact)).evidence_id, "e1")
        for name, malformed in (("not-object.json", b"[]"), ("duplicate-key.json", b'{"x":1,"x":2}')):
            (self.root/name).write_bytes(malformed)
            with self.assertRaises(ScarInputError) as cm:
                load_evidence(self.root, _reference(name, malformed))
            self.assertEqual(cm.exception.code, "EVIDENCE_RECORD_INVALID")
        for size in (MAX_EVIDENCE_BYTES + 1, 2**22):
            path = self.root / f"size-{size}.json"
            with path.open("wb") as handle:
                handle.truncate(size)
            ref = _reference(path.name, b"")
            ref["sha256"] = "0" * 64
            with self.assertRaises(ScarInputError) as cm:
                load_evidence(self.root, ref)
            self.assertEqual(cm.exception.code, "EVIDENCE_TOO_LARGE")
        # Instrument the evidence helper itself: its only byte reads are bounded descriptor reads.
        target = self.root / "large.bin"
        target.write_bytes(b"x" * (MAX_EVIDENCE_BYTES + 500))
        observed = 0
        original = os.read
        def count(fd: int, amount: int) -> bytes:
            nonlocal observed
            block = original(fd, amount)
            observed += len(block)
            return block
        expected_raw = b"x" * (MAX_EVIDENCE_BYTES + 500)
        with patch("scar_core.secureio.os.read", count), self.assertRaises(ScarInputError):
            load_evidence(self.root, _reference("large.bin", expected_raw))
        self.assertEqual(observed, MAX_EVIDENCE_BYTES + 1)

    def test_nonregular_fifo_and_path_forms_fail_closed(self) -> None:
        fifo = self.root / "pipe"
        os.mkfifo(fifo)
        with self.assertRaises(ScarInputError) as cm:
            read_bounded_path(fifo, 10, "INPUT_TOO_LARGE")
        self.assertEqual(cm.exception.code, "INPUT_NOT_REGULAR_FILE")
        for path in ("../outside", "/absolute", "a//b", "a/./b", "a\\b", ""):
            root_fd = open_root(self.root)
            try:
                with self.assertRaises(ScarInputError) as cm:
                    open_relative_regular(root_fd, path)
                self.assertEqual(cm.exception.code, "UNSAFE_EVIDENCE_PATH")
            finally:
                os.close(root_fd)
        with self.assertRaises(ScarInputError) as cm:
            load_evidence(self.root, _reference(".", b""))
        self.assertEqual(cm.exception.code, "UNSAFE_EVIDENCE_PATH")

    def test_symlinks_root_symlink_and_ancestor_symlink_rejected(self) -> None:
        raw = _record()
        (self.root / "real").mkdir()
        (self.root / "real" / "e.json").write_bytes(raw)
        (self.root / "link").symlink_to(self.root / "real", target_is_directory=True)
        with self.assertRaises(ScarInputError):
            load_evidence(self.root, _reference("link/e.json", raw))
        root_link = self.base / "root-link"
        root_link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ScarInputError):
            open_root(root_link)
        file_link = self.root / "file-link"
        file_link.symlink_to(self.root / "real" / "e.json")
        with self.assertRaises(ScarInputError):
            load_evidence(self.root, _reference("file-link", raw))
        loop = self.root / "loop"
        loop.symlink_to(loop)
        with self.assertRaises(ScarInputError):
            load_evidence(self.root, _reference("loop", raw))
        with self.assertRaises(ScarInputError) as cm:
            load_evidence(self.root, _reference("real", raw))
        self.assertEqual(cm.exception.code, "EVIDENCE_NOT_REGULAR_FILE")

    def test_deterministic_leaf_symlink_swap_is_blocked(self) -> None:
        raw = _record()
        external = self.base / "outside.json"
        external.write_bytes(raw)
        target = self.root / "race.json"
        target.write_bytes(b"not the same record")
        original_open = os.open
        swapped = False
        def swap_then_open(path, flags, *args, **kwargs):
            nonlocal swapped
            if path == "race.json" and kwargs.get("dir_fd") is not None and not swapped:
                target.unlink()
                target.symlink_to(external)
                swapped = True
            return original_open(path, flags, *args, **kwargs)
        with patch("scar_core.secureio.os.open", swap_then_open):
            with self.assertRaises(ScarInputError) as cm:
                load_evidence(self.root, _reference("race.json", raw))
        self.assertTrue(swapped)
        self.assertIn(cm.exception.code, {"SYMLINK_EVIDENCE_PATH", "EVIDENCE_OPEN_FAILED"})

    def test_ancestor_swap_is_blocked_and_regular_replacement_is_digest_checked(self) -> None:
        raw = _record()
        (self.root / "parent").mkdir()
        (self.root / "parent" / "e.json").write_bytes(raw)
        external = self.base / "external"
        external.mkdir()
        (external / "e.json").write_bytes(raw)
        original_open = os.open
        swapped = False
        def swap_ancestor(path, flags, *args, **kwargs):
            nonlocal swapped
            if path == "parent" and kwargs.get("dir_fd") is not None and not swapped:
                (self.root / "parent").rename(self.root / "parent-old")
                (self.root / "parent").symlink_to(external, target_is_directory=True)
                swapped = True
            return original_open(path, flags, *args, **kwargs)
        with patch("scar_core.secureio.os.open", swap_ancestor):
            with self.assertRaises(ScarInputError):
                load_evidence(self.root, _reference("parent/e.json", raw))
        self.assertTrue(swapped)
        # A swapped regular in-root file is opened by descriptor and rejected on digest mismatch.
        target = self.root / "plain.json"
        target.write_bytes(raw)
        digest = _reference("plain.json", raw)
        target.write_bytes(raw.replace(b"fixture", b"changed"))
        with self.assertRaises(ScarInputError) as cm:
            load_evidence(self.root, digest)
        self.assertEqual(cm.exception.code, "EVIDENCE_DIGEST_MISMATCH")

    def test_concurrent_growth_is_bounded(self) -> None:
        target = self.root / "growing.bin"
        target.write_bytes(b"x" * (MAX_INPUT_BYTES + 4096))
        stop = threading.Event()
        def writer() -> None:
            with target.open("ab", buffering=0) as handle:
                while not stop.is_set():
                    handle.write(b"x" * 8192)
        thread = threading.Thread(target=writer, daemon=True)
        thread.start()
        observed = 0
        original = os.read
        def count(fd: int, amount: int) -> bytes:
            nonlocal observed
            block = original(fd, amount)
            observed += len(block)
            return block
        try:
            with patch("scar_core.secureio.os.read", count), self.assertRaises(ScarInputError):
                read_bounded_path(target, MAX_INPUT_BYTES, "INPUT_TOO_LARGE")
        finally:
            stop.set()
            thread.join(timeout=2)
        self.assertLessEqual(observed, MAX_INPUT_BYTES + 1)

    def test_cli_redacts_identifiers_and_errors(self) -> None:
        sentinel = "SENSITIVE_IDENTITY_SENTINEL_77"
        env = json.loads((_DATA / "envelope.json").read_text(encoding="utf-8"))
        env["workflow_id"] = sentinel
        env["scope"]["repository_id"] = sentinel
        redacted = _redact_identities({"workflow_id": sentinel, "scope": {"repository_id": sentinel}})
        self.assertNotIn(sentinel, json.dumps(redacted))
        (self.base / (sentinel + ".json")).write_text("{bad", encoding="utf-8")
        from io import StringIO
        import contextlib
        err = StringIO()
        with contextlib.redirect_stderr(err):
            rc = main(["inspect", "--input", str(self.base / (sentinel + ".json")), "--root", str(self.root)])
        self.assertEqual(rc, 2)
        self.assertNotIn(sentinel, err.getvalue())
        self.assertNotIn(str(self.base), err.getvalue())
        self.assertNotIn("bad", err.getvalue())

        env["workflow_id"] = sentinel
        env["scope"]["repository_id"] = sentinel
        valid_input = self.base / "untrusted-envelope.json"
        valid_input.write_text(json.dumps(env), encoding="utf-8")
        out = StringIO()
        with contextlib.redirect_stdout(out):
            rc = main(["inspect", "--input", str(valid_input), "--root", str(_DATA), "--format", "json"])
        self.assertEqual(rc, 0)
        self.assertNotIn(sentinel, out.getvalue())
        self.assertNotIn(str(self.base), out.getvalue())

    def test_untrusted_input_identity_is_not_returned_by_cli_projection(self) -> None:
        sentinel = "SENSITIVE_SOURCE_NAME_991"
        result = _redact_identities({"workflow_id": sentinel, "scope": {"repository_id": sentinel}})
        self.assertNotIn(sentinel, json.dumps(result))

    def test_parser_state_and_schema_limits_fail_closed(self) -> None:
        malformed = [b"\xff", b"{broken", b'{"x":1,"x":2}',
                     (b"[" * (MAX_DEPTH + 2)) + b"0" + (b"]" * (MAX_DEPTH + 2))]
        for raw in malformed:
            with self.subTest(raw_len=len(raw)), self.assertRaises(ScarInputError):
                parse_json_bytes(raw)
        env = json.loads((_DATA / "envelope.json").read_text(encoding="utf-8"))
        many_rows = json.loads(json.dumps(env))
        many_rows["events"] = [{}] * 257
        with self.assertRaises(ScarInputError) as cm:
            validate_envelope(many_rows)
        self.assertEqual(cm.exception.code, "ROW_LIMIT")
        over_obligations = json.loads(json.dumps(env))
        over_obligations["obligations"] *= 2
        with self.assertRaises(ScarInputError) as cm:
            validate_envelope(over_obligations)
        self.assertEqual(cm.exception.code, "OBLIGATION_LIMIT")
        states = _enumerate_states([{"obligation_id":f"o{i}","depends_on":[]} for i in range(9)], (), 256)
        self.assertEqual(states, [])


if __name__ == "__main__":
    unittest.main()
