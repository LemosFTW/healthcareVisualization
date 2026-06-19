"""REST handler for POST /messages — processes a raw message through the pipeline."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, List, Optional  # noqa: F401

from fastapi.responses import JSONResponse
from healthcare_sdk.contracts import MessageEnvelope, RawMessage
from pydantic import BaseModel


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


def _serialize_stored(record: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a storage read() dict for JSON serialization."""
    normalized = record.get("normalized_payload") or {}
    warnings: List[str] = (
        normalized.get("warnings", []) if isinstance(normalized, dict) else []
    )
    created_at = record.get("created_at")
    return {
        "id": record.get("id"),
        "protocol": record.get("protocol"),
        "message_type": record.get("message_type"),
        "status": record.get("status"),
        "raw_payload": record.get("raw_payload"),
        "decoded_payload": record.get("decoded_payload"),
        "normalized_payload": normalized,
        "warnings": warnings,
        "errors": record.get("errors") or [],
        "created_at": created_at.isoformat()
        if hasattr(created_at, "isoformat")
        else str(created_at or ""),
    }


def create_query_message_handler(usecase):
    """Return an async FastAPI handler for GET /messages/{id} bound to *usecase*."""

    async def handler(id: str) -> JSONResponse:
        record = usecase.execute(id)
        if not record:
            return JSONResponse(
                status_code=404,
                content={
                    "type": "about:blank",
                    "title": "Not Found",
                    "status": 404,
                    "detail": f"Message with id '{id}' was not found",
                },
            )
        return JSONResponse(content=_serialize_stored(record), status_code=200)

    return handler


def create_list_logs_handler(usecase):
    """Handler for GET /logs."""

    async def handler(
        page: int = 1,
        page_size: int = 10,
        status: Optional[str] = None,
    ) -> JSONResponse:
        records = usecase.execute(page=page, page_size=page_size, status=status)
        serialized = [
            {
                **r,
                "created_at": r["created_at"].isoformat()
                if hasattr(r.get("created_at"), "isoformat")
                else str(r.get("created_at") or ""),
                "updated_at": r["updated_at"].isoformat()
                if hasattr(r.get("updated_at"), "isoformat")
                else str(r.get("updated_at") or ""),
            }
            for r in records
        ]
        return JSONResponse(
            content={"page": page, "page_size": page_size, "items": serialized},
            status_code=200,
        )

    return handler


def create_list_messages_handler(usecase):
    """Handler for GET /messages."""

    async def handler(
        page: int = 1,
        page_size: int = 10,
        review_status: Optional[str] = None,
    ) -> JSONResponse:
        records = usecase.execute(
            page=page,
            page_size=page_size,
            review_status=review_status,
        )
        return JSONResponse(
            content={"page": page, "page_size": page_size, "items": [
                _serialize_stored(r) for r in records
            ]},
            status_code=200,
        )

    return handler


def create_commit_message_handler(usecase):
    """Handler for POST /messages/{id}/commit."""

    async def handler(id: str) -> JSONResponse:
        found = usecase.execute(id)
        if not found:
            return JSONResponse(
                status_code=404,
                content={
                    "type": "about:blank",
                    "title": "Not Found",
                    "status": 404,
                    "detail": f"Message with id '{id}' was not found",
                },
            )
        return JSONResponse(
            content={"id": id, "review_status": "approved"},
            status_code=200,
        )

    return handler


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
        envelope = await asyncio.to_thread(usecase.execute, raw)
        return JSONResponse(content=_serialize_envelope(envelope), status_code=200)

    return handler
