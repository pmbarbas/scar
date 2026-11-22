"""SCAR evidence-state research toolkit; outputs are advisory."""

from .contracts import (
    INPUT_SCHEMA,
    OUTPUT_SCHEMA,
    RecoveryAssessment,
    ScarInputError,
    validate_assessment_roundtrip,
    validate_envelope,
)
from .recovery import inspect_evidence
from .verify import (
    DigestOnlyVerifier,
    EvidencePayload,
    EvidenceVerifier,
    VerificationResult,
)

__version__ = "0.2.0"
__all__ = [
    "INPUT_SCHEMA",
    "OUTPUT_SCHEMA",
    "RecoveryAssessment",
    "ScarInputError",
    "validate_assessment_roundtrip",
    "validate_envelope",
    "inspect_evidence",
    "DigestOnlyVerifier",
    "EvidencePayload",
    "EvidenceVerifier",
    "VerificationResult",
]
