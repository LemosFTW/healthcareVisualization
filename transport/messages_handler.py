"""REST handler for POST /messages — processes a raw message through the full pipeline."""
from __future__ import annotations
import uuid
from typing import Any, Dict, List, Optional

from fastapi.responses import JSONResponse
from pydantic import BaseModel

from healthcare_sdk.contracts import MessageEnvelope, RawMessage


class MessageRequest(BaseModel):
    protocol: str
    raw_payload: str
    id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    message_type: Optional[str] = None


def _serialize_envelope(envelope: MessageEnvelope) -> Dict[str, Any]:
    normalized = envelope.normalized_payload or {}
    warnings: List[str] = (
        normalized.get("warnings", []) if isinstance(normalized, dict) else []
    )
    return {
        "id": envelope.id,
        "protocol": envelope.protocol,
        "message_type": envelope.message_type,
        "status": envelope.status,
        "decoded_payload": envelope.decoded_payload,
        "normalized_payload": envelope.normalized_payload,
        "warnings": warnings,
        "errors": [
            {
                "code": e.code,
                "message": e.message,
                "stage": e.stage,
                "context": e.context,
            }
            for e in envelope.errors
        ],
    }


def create_process_message_handler(usecase):
    """Return an async FastAPI handler for POST /messages bound to *usecase*."""

    async def handler(body: MessageRequest) -> JSONResponse:
        raw = RawMessage(
            id=body.id or str(uuid.uuid4()),
            protocol=body.protocol,
            raw_payload=body.raw_payload,
            metadata=body.metadata or {},
            message_type=body.message_type,
        )
        envelope = usecase.execute(raw)
        return JSONResponse(content=_serialize_envelope(envelope), status_code=200)

    return handler
