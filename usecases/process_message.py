from __future__ import annotations

import logging

from healthcare_sdk.contracts import STATUS_ERROR
from healthcare_sdk.usecases import DefaultHealthCareUsecase

logger = logging.getLogger(__name__)

_REVIEW_STATUS_KEY = "review_status"
_REVIEW_PENDING = "pending"


class ProcessMessageUsecase(DefaultHealthCareUsecase):
    """Extends the SDK pipeline: marks every persisted envelope as pending
    human review and ensures error envelopes are also stored."""

    def _store(self, envelope):
        envelope.metadata[_REVIEW_STATUS_KEY] = _REVIEW_PENDING
        return super()._store(envelope)

    def execute(self, raw_message):
        envelope = super().execute(raw_message)
        if envelope.status == STATUS_ERROR:
            envelope.metadata[_REVIEW_STATUS_KEY] = _REVIEW_PENDING
            try:
                self.storage.save(envelope)
            except Exception as exc:
                logger.warning("Failed to persist error envelope: %s", exc)
        return envelope
