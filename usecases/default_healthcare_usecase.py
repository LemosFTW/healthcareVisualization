from __future__ import annotations
from healthcare_sdk import HealthCareUsecase, MessageEnvelope, RawMessage, STATUS_RECEIVED


class DefaultHealthCareUsecase(HealthCareUsecase):
    """Placeholder — full pipeline (decode→validate→normalize→store) implemented in Story 1.8."""

    def execute(self, raw_message: RawMessage) -> MessageEnvelope:
        return MessageEnvelope(
            id=raw_message.id,
            protocol=raw_message.protocol,
            message_type=raw_message.message_type or "",
            raw_payload=raw_message.raw_payload,
            metadata=raw_message.metadata,
            status=STATUS_RECEIVED,
        )
