from __future__ import annotations

from healthcare_sdk import HealthCareStorage
from healthcare_sdk.contracts import MessageEnvelope, RawMessage
from healthcare_sdk.usecases import HealthCareUsecase


class CommitMessageUsecase(HealthCareUsecase):
    """Explicitly persists a raw message as a committed envelope.

    Used when the transport layer needs to force-save a message
    without running the full decode/validate/normalize pipeline.
    """

    def __init__(self, storage : HealthCareStorage) -> None:
        self._storage = storage

    def execute(self, raw_message: RawMessage) -> MessageEnvelope:
        envelope = MessageEnvelope(
            id=raw_message.id,
            protocol=raw_message.protocol,
            message_type=raw_message.message_type or "",
            raw_payload=raw_message.raw_payload,
            metadata={**raw_message.metadata, "mode": "commit"},
        )
        self._storage.save(envelope)
        return envelope
