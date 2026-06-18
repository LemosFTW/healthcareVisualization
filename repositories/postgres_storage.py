from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from healthcare_sdk import HealthCareStorage
from healthcare_sdk.contracts import STATUS_NORMALIZED, STATUS_STORED, MessageEnvelope
from healthcare_sdk.repositories.base import Base
from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, Session, mapped_column


class _HealthcareMessageLog(Base):
    """ORM model that persists all MessageEnvelope fields,
    including payloads and errors."""

    __tablename__ = "healthcare_message_log"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    protocol: Mapped[str] = mapped_column(String(50), nullable=False)
    message_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    raw_payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decoded_payload: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    normalized_payload: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    errors: Mapped[Optional[Any]] = mapped_column(JSON, nullable=True)
    review_status: Mapped[Optional[str]] = mapped_column(
        SAEnum("pending", "approved", name="review_status_enum"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    @classmethod
    def from_envelope(cls, envelope: MessageEnvelope) -> "_HealthcareMessageLog":
        errors_data = [
            {
                "code": e.code,
                "message": e.message,
                "stage": e.stage,
                "context": e.context,
            }
            for e in (envelope.errors or [])
        ]
        raw = envelope.raw_payload
        raw_str = raw.decode("latin-1") if isinstance(raw, bytes) else (raw or "")
        return cls(
            id=str(envelope.id) if envelope.id else str(uuid.uuid4()),
            protocol=envelope.protocol,
            message_type=envelope.message_type or "",
            status=envelope.status,
            raw_payload=raw_str,
            decoded_payload=envelope.decoded_payload,
            normalized_payload=envelope.normalized_payload,
            errors=errors_data,
            review_status=envelope.metadata.get("review_status"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "protocol": self.protocol,
            "message_type": self.message_type,
            "status": self.status,
            "raw_payload": self.raw_payload,
            "decoded_payload": self.decoded_payload,
            "normalized_payload": self.normalized_payload,
            "errors": self.errors,
            "review_status": self.review_status,
            "created_at": self.created_at,
        }


class PostgreSqlStorage(HealthCareStorage):
    """Project-level storage implementing HealthCareStorage
    with full envelope persistence.

    Stores all MessageEnvelope fields (decoded_payload, normalized_payload, errors).
    Uses Base.metadata.create_all(engine) to create tables if they do not exist.
    Compatible with both PostgreSQL and SQLite engines (used in tests).
    """

    def __init__(self, engine: Any) -> None:
        Base.metadata.create_all(engine)
        self._engine = engine

    def connection(self) -> Session:
        return Session(self._engine)

    def save(self, envelope: MessageEnvelope) -> str:
        with Session(self._engine) as session:
            log = _HealthcareMessageLog.from_envelope(envelope)
            # The SDK calls save() before setting STATUS_STORED on the envelope.
            # Upgrade normalized → stored here so the persisted record
            # reflects final state.
            if log.status == STATUS_NORMALIZED:
                log.status = STATUS_STORED
            session.merge(log)
            session.commit()
            return log.id

    def read(self, query: Dict[str, Any]) -> Dict[str, Any]:
        with Session(self._engine) as session:
            if "id" in query:
                log = session.get(_HealthcareMessageLog, query["id"])
                if log is None:
                    return {}
                return log.to_dict()
        return {}

    def update(self, query: Dict[str, Any], data: Dict[str, Any]) -> bool:
        with Session(self._engine) as session:
            if "id" in query:
                log = session.get(_HealthcareMessageLog, query["id"])
                if log is None:
                    return False
                for key, value in data.items():
                    if hasattr(log, key):
                        setattr(log, key, value)
                session.commit()
                return True
        return False

    def delete(self, query: Dict[str, Any]) -> bool:
        with Session(self._engine) as session:
            if "id" in query:
                log = session.get(_HealthcareMessageLog, query["id"])
                if log is None:
                    return False
                session.delete(log)
                session.commit()
                return True
        return False
