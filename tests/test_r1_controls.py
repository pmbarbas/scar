from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from scar_core.demo import _DATA, _DemoVerifier
from scar_core.recovery import inspect_evidence
from scar_core.verify import VerificationResult


class NonIndependent:
    verifier_id = "test-only"

    def __init__(self, delegate):
        self.delegate = delegate

    def verify(self, **kwargs):
        result = self.delegate.verify(**kwargs)
        return VerificationResult(result.verified_polarity, result.reason_code,
                                  result.detail, result.evidence_integrity, False)


class R1TrustControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = json.loads((_DATA / "envelope.json").read_text(encoding="utf-8"))
        rules = json.loads((_DATA / "verifier_rules.json").read_text(encoding="utf-8"))["rules"]
        cls.delegate = _DemoVerifier(rules)

    def assess(self, envelope, verifier=None):
        return inspect_evidence(envelope, _DATA, verifier or self.delegate, envelope["policy"]).to_dict()

    def test_non_independent_verification_cannot_promote_claims(self):
        result = self.assess(copy.deepcopy(self.original), NonIndependent(self.delegate))
        self.assertEqual(result["supported_completed_obligations"], [])
        self.assertIn("VERIFIER_NOT_INDEPENDENT",
                      {row["reason_code"] for row in result["invalid_or_unverified_claims"]})

    def test_origin_flag_is_not_authority(self):
        env = copy.deepcopy(self.original)
        for claim in env["claims"]:
            claim["origin_authenticated"] = True
        result = self.assess(env, __import__("scar_core").DigestOnlyVerifier())
        self.assertEqual(result["supported_completed_obligations"], [])
        self.assertTrue(result["invalid_or_unverified_claims"])

    def test_transitive_inflight_parent_blocks_descendant_completion(self):
        env = copy.deepcopy(self.original)
        root_id = env["events"][0]["event_id"]
        env["events"][0]["delivery"] = "IN_FLIGHT"
        result = self.assess(env)
        self.assertTrue(result["missing_causal_parents"] or result["invalid_or_unverified_claims"])
        self.assertNotIn("O1-interface", result["supported_completed_obligations"])
        self.assertNotIn("O2-caller", result["supported_completed_obligations"])
        self.assertTrue(any(root_id in str(row) for row in result["missing_causal_parents"]))
        self.assertTrue(result["host_authorization_required"])


if __name__ == "__main__":
    unittest.main()
