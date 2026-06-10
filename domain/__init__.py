"""Domain layer — re-exports SDK contracts as first-class domain types."""

from healthcare_sdk.contracts import (
    RawMessage,
    MessageEnvelope,
    ValidationResult,
    ErrorDetail,
    STATUS_RECEIVED,
    STATUS_DECODED,
    STATUS_VALIDATED,
    STATUS_NORMALIZED,
    STATUS_STORED,
    STATUS_ERROR,
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
