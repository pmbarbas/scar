from __future__ import annotations
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from scar_core import DigestOnlyVerifier, ScarInputError, validate_assessment_roundtrip  # noqa: E402
from scar_core.demo import run_demo  # noqa: E402
from scar_core.contracts import parse_json_bytes  # noqa: E402


class CoreContractTests(unittest.TestCase):
    def test_demo_recommends_fresh_query_and_never_grants_authority(self):
        result, story = run_demo()
        self.assertIn("stale", story)
        self.assertEqual(result["outcome"], "STALE_EPOCH")
        self.assertEqual(
            result["recommendations"][0]["query_id"], "verify-O4-integration"
        )
        self.assertTrue(result["host_authorization_required"])
        self.assertEqual(result["recommendations"][0]["kind"], "EVIDENCE_REQUEST")

    def test_assessment_json_roundtrip(self):
        result, _ = run_demo()
        encoded = json.dumps(result, sort_keys=True)
        decoded = json.loads(encoded)
        self.assertEqual(validate_assessment_roundtrip(decoded), decoded)

    def test_packaged_schema_is_valid_json(self):
        schema_path = (
            ROOT / "src/scar_core/data/evidence-v0.schema.json"
        )
        schema = json.loads(schema_path.read_text())
        self.assertEqual(schema["$id"], "scar.evidence.v0")

    def test_cli_demo_matches_api(self):
        proc = subprocess.run(
            [sys.executable, "-m", "scar_core", "demo"],
            cwd=ROOT,
            env={
                **os.environ,
                "PYTHONPATH": str(ROOT / "src"),
            },
            capture_output=True,
            text=True,
            check=True,
        )
        lines = proc.stdout.splitlines()
        json_start = next(i for i, x in enumerate(lines) if x.startswith("{"))
        cli = json.loads("\n".join(lines[json_start:]))
        api, _ = run_demo()
        self.assertEqual(cli, api)

    def test_cli_top_level_help(self):
        proc = subprocess.run(
            [sys.executable, "-m", "scar_core"],
            cwd=ROOT,
            env={
                **os.environ,
                "PYTHONPATH": str(ROOT / "src"),
            },
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("inspect", proc.stdout)

    def test_duplicate_json_key_and_oversize_rejected(self):
        with self.assertRaises(ScarInputError) as cm:
            parse_json_bytes(b'{"a":1,"a":2}')
        self.assertEqual(cm.exception.code, "DUPLICATE_JSON_KEY")
        with self.assertRaises(ScarInputError) as cm:
            parse_json_bytes(b" " * 1_048_577)
        self.assertEqual(cm.exception.code, "INPUT_TOO_LARGE")

    def test_digest_only_verifier_never_claims_semantic_support(self):
        self.assertEqual(DigestOnlyVerifier().verifier_id, "digest-only-v1")
        result, _ = run_demo()
        self.assertIn("digest binds bytes", result["assumptions"][1])


if __name__ == "__main__":
    unittest.main()
