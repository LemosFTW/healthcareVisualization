from __future__ import annotations

import logging

from healthcare_sdk.contracts import STATUS_ERROR
from healthcare_sdk.repositories.messageLog import MessageLog
from healthcare_sdk.usecases import DefaultHealthCareUsecase

logger = logging.getLogger(__name__)

_REVIEW_STATUS_KEY = "review_status"
_REVIEW_PENDING = "pending"


class ProcessMessageUsecase(DefaultHealthCareUsecase):
    """Extends the SDK pipeline: logs each stage, marks every persisted envelope
    as pending human review and ensures error envelopes are also stored."""

    def _decode(self, raw_message, envelope):
        logger.info(
            "[%s] stage=decode started protocol=%s", envelope.id, envelope.protocol
        )
        result = super()._decode(raw_message, envelope)
        if result is None:
            logger.warning(
                "[%s] stage=decode failed errors=%s", envelope.id, envelope.errors
            )
        else:
            logger.info("[%s] stage=decode completed", envelope.id)
        return result

    def _validate(self, envelope):
        logger.info("[%s] stage=validate started", envelope.id)
        result = super()._validate(envelope)
        if result is None:
            logger.warning(
                "[%s] stage=validate failed errors=%s", envelope.id, envelope.errors
            )
        else:
            logger.info("[%s] stage=validate completed", envelope.id)
        return result

    def _normalize(self, envelope):
        logger.info("[%s] stage=normalize started", envelope.id)
        result = super()._normalize(envelope)
        if result is None:
            logger.warning(
                "[%s] stage=normalize failed errors=%s", envelope.id, envelope.errors
            )
        else:
            logger.info("[%s] stage=normalize completed", envelope.id)
        return result

    def _store(self, envelope):
        envelope.metadata[_REVIEW_STATUS_KEY] = _REVIEW_PENDING
        logger.info("[%s] stage=store started review_status=pending", envelope.id)
        result = super()._store(envelope)
        if result is None:
            logger.warning(
                "[%s] stage=store failed errors=%s", envelope.id, envelope.errors
            )
        else:
            logger.info(
                "[%s] stage=store completed status=%s", envelope.id, envelope.status
            )
        return result

    def execute(self, raw_message):
        logger.info("[%s] pipeline started", raw_message.id)
        envelope = super().execute(raw_message)
        if envelope.status == STATUS_ERROR:
            envelope.metadata[_REVIEW_STATUS_KEY] = _REVIEW_PENDING
            try:
                self.storage.save(envelope)
            except Exception as exc:
                logger.warning(
                    "[%s] Failed to persist error envelope: %s", envelope.id, exc
                )
        logger.info("[%s] pipeline finished status=%s", envelope.id, envelope.status)
        try:
            with self.storage.connection() as session:
                session.add(MessageLog.from_envelope(envelope))
                session.commit()
        except Exception as exc:
            logger.warning("[%s] Failed to write message_log: %s", envelope.id, exc)
        return envelope
