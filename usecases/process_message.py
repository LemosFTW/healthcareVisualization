from __future__ import annotations

import logging

from healthcare_sdk.contracts import STATUS_ERROR
from healthcare_sdk.usecases import DefaultHealthCareUsecase

logger = logging.getLogger(__name__)


class ProcessMessageUsecase(DefaultHealthCareUsecase):
    """Extends the SDK pipeline to persist error envelopes on decode/validate
    failure."""

    def execute(self, raw_message):
        envelope = super().execute(raw_message)
        if envelope.status == STATUS_ERROR:
            try:
                self.storage.save(envelope)
            except Exception as exc:
                logger.warning("Failed to persist error envelope: %s", exc)
        return envelope
