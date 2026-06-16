"""Domain layer — re-exports SDK contracts as first-class domain types."""

from healthcare_sdk.contracts import (
    STATUS_DECODED,
    STATUS_ERROR,
    STATUS_NORMALIZED,
    STATUS_RECEIVED,
    STATUS_STORED,
    STATUS_VALIDATED,
    ErrorDetail,
    MessageEnvelope,
    RawMessage,
    ValidationResult,
)

__all__ = [
    "RawMessage",
    "MessageEnvelope",
    "ValidationResult",
    "ErrorDetail",
    "STATUS_RECEIVED",
    "STATUS_DECODED",
    "STATUS_VALIDATED",
    "STATUS_NORMALIZED",
    "STATUS_STORED",
    "STATUS_ERROR",
]
