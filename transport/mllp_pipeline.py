"""MLLP pipeline integration — bridges MllpConnector.receive() to a usecase."""
from __future__ import annotations
import logging
from typing import Any

from healthcare_sdk.contracts import STATUS_ERROR

logger = logging.getLogger(__name__)


def create_mllp_pipeline_loop(connector, usecase, storage):
    """Return a callable that processes MLLP messages through the pipeline indefinitely.

    The loop:
    1. Blocks on connector.receive() until a RawMessage arrives.
    2. Calls usecase.execute(raw_message) to run the full pipeline.
    3. Persists error envelopes explicitly (the SDK skips storage on decode/validate failure).
    4. Catches exceptions so one bad message never stops the loop.

    The MLLP ACK is sent by MllpConnector._handle_client() immediately on receipt —
    before receive() returns — so ACK delivery is independent of pipeline outcome.
    """

    def _loop() -> None:
        logger.info("MLLP pipeline loop started")
        while True:
            try:
                raw_msg = connector.receive()
                envelope = usecase.execute(raw_msg)

                if envelope.status == STATUS_ERROR:
                    try:
                        storage.save(envelope)
                    except Exception as exc:
                        logger.warning("Failed to persist MLLP error envelope: %s", exc)

            except Exception as exc:
                logger.error("Unhandled error in MLLP pipeline loop: %s", exc)

    return _loop
