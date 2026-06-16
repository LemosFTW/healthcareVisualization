from __future__ import annotations

import logging

from healthcare_sdk.contracts import STATUS_ERROR
from healthcare_sdk.usecases import DefaultHealthCareUsecase

logger = logging.getLogger(__name__)


class ProcessMessageUsecase:
    """Orchestrates the full pipeline: decode → validate → normalize → store.

    Wraps the SDK's DefaultHealthCareUsecase and adds explicit persistence of
    error envelopes, which the SDK skips on decode/validate failure.
    """

    def __init__(self, decoder, validator, normalizer, storage) -> None:
        self._inner = DefaultHealthCareUsecase(
            decoder=decoder,
            validator=validator,
            normalizer=normalizer,
            storage=storage,
        )
        self._storage = storage

    def execute(self, raw_message):
        envelope = self._inner.execute(raw_message)
        if envelope.status == STATUS_ERROR:
            try:
                self._storage.save(envelope)
            except Exception as exc:
                logger.warning("Failed to persist error envelope: %s", exc)
        return envelope
