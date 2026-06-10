"""Tests for Story 1.8: POST /messages REST endpoint."""
import pytest
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from unittest.mock import MagicMock

from healthcare_sdk import RestController
from healthcare_sdk.contracts import STATUS_STORED, STATUS_ERROR
from healthcare_sdk.usecases import DefaultHealthCareUsecase

from infrastructure import (
    Hl7Validator,
    HealthcareNormalizer,
    HealthcareDecoderRouter,
    Hl7V2Decoder,
    PostgreSqlStorage,
)
from transport.messages_handler import create_process_message_handler


VALID_HL7 = (
    r"MSH|^~\&|SendApp|SendFac|RecApp|RecFac|20230601120000||ADT^A01|MSG001|P|2.3"
    + "\rPID|1||12345^^^MRN||Doe^John^A||19800101|M"
)

# Same as VALID_HL7 but includes an OBX so the normalizer forwards observations to the AI helper
VALID_HL7_WITH_OBX = (
    r"MSH|^~\&|LAB|HOSP|EHR|CLINIC|20230601120000||ORU^R01|MSG002|P|2.3"
    + "\rPID|1||99999^^^MRN||Smith^Jane||19900101|F"
    + "\rOBR|1|O001|F001|CBC^Complete Blood Count"
    + "\rOBX|1|NM|HR^Heart Rate||0|bpm|60-100|L||F"
)

MALFORMED_HL7 = "NOT_HL7_AT_ALL"


def _make_engine():
    """StaticPool keeps a single connection so in-memory tables survive across sessions."""
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _build_client(extra_decoder: dict | None = None):
    """Build a TestClient with the full pipeline wired to SQLite in-memory."""
    engine = _make_engine()
    storage = PostgreSqlStorage(engine)

    hl7_decoder = Hl7V2Decoder()
    decoders = {"hl7v2": hl7_decoder}
    if extra_decoder:
        decoders.update(extra_decoder)
    router = HealthcareDecoderRouter(decoders)

    validator = Hl7Validator()
    normalizer = HealthcareNormalizer()
    # No AI helper — warnings will be []

    usecase = DefaultHealthCareUsecase(
        decoder=router,
        validator=validator,
        normalizer=normalizer,
        storage=storage,
    )

    controller = RestController()

    @controller.app.exception_handler(RequestValidationError)
    async def _val_err(request, exc):
        return JSONResponse(
            status_code=422,
            content={
                "type": "about:blank",
                "title": "Unprocessable Content",
                "status": 422,
                "detail": str(exc),
            },
        )

    controller.add_endpoint("/messages", "POST", create_process_message_handler(usecase))
    return TestClient(controller.app, raise_server_exceptions=False)


# AC1: Valid payload → HTTP 200 with status="stored" and all envelope fields
def test_post_valid_hl7_returns_200_with_stored_status():
    client = _build_client()
    resp = client.post("/messages", json={"protocol": "hl7v2", "raw_payload": VALID_HL7})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == STATUS_STORED


def test_post_valid_hl7_response_contains_decoded_payload():
    client = _build_client()
    resp = client.post("/messages", json={"protocol": "hl7v2", "raw_payload": VALID_HL7})
    body = resp.json()
    assert "decoded_payload" in body
    assert body["decoded_payload"] is not None
    assert "MSH" in body["decoded_payload"]


def test_post_valid_hl7_response_contains_normalized_payload():
    client = _build_client()
    resp = client.post("/messages", json={"protocol": "hl7v2", "raw_payload": VALID_HL7})
    body = resp.json()
    assert "normalized_payload" in body
    assert body["normalized_payload"] is not None


def test_post_valid_hl7_response_has_empty_errors():
    client = _build_client()
    resp = client.post("/messages", json={"protocol": "hl7v2", "raw_payload": VALID_HL7})
    body = resp.json()
    assert body["errors"] == []


def test_post_valid_hl7_response_has_warnings_field():
    client = _build_client()
    resp = client.post("/messages", json={"protocol": "hl7v2", "raw_payload": VALID_HL7})
    body = resp.json()
    assert "warnings" in body
    assert isinstance(body["warnings"], list)


# AC2: Malformed HL7 → HTTP 200 with status="error" and errors populated, envelope persisted
def test_post_malformed_hl7_returns_200_with_error_status():
    client = _build_client()
    resp = client.post("/messages", json={"protocol": "hl7v2", "raw_payload": MALFORMED_HL7})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == STATUS_ERROR


def test_post_malformed_hl7_response_has_decode_error():
    client = _build_client()
    resp = client.post("/messages", json={"protocol": "hl7v2", "raw_payload": MALFORMED_HL7})
    body = resp.json()
    assert len(body["errors"]) >= 1
    stages = [e["stage"] for e in body["errors"]]
    assert "decode" in stages


# AC3: Missing required body fields → HTTP 422 RFC 9457 Problem Details
def test_post_missing_protocol_returns_422():
    client = _build_client()
    resp = client.post("/messages", json={"raw_payload": VALID_HL7})
    assert resp.status_code == 422


def test_post_missing_raw_payload_returns_422():
    client = _build_client()
    resp = client.post("/messages", json={"protocol": "hl7v2"})
    assert resp.status_code == 422


def test_post_empty_body_returns_422():
    client = _build_client()
    resp = client.post("/messages", json={})
    assert resp.status_code == 422


def test_post_422_response_is_rfc9457_problem_details():
    client = _build_client()
    resp = client.post("/messages", json={})
    body = resp.json()
    assert body["type"] == "about:blank"
    assert body["status"] == 422
    assert "title" in body
    assert "detail" in body


# AC4: Payload with anomaly detected → HTTP 200 with warnings non-empty
def test_post_with_ai_helper_returns_warnings():
    engine = _make_engine()
    storage = PostgreSqlStorage(engine)
    router = HealthcareDecoderRouter({"hl7v2": Hl7V2Decoder()})
    validator = Hl7Validator()
    normalizer = HealthcareNormalizer()

    ai_mock = MagicMock()
    ai_mock.generateResponse.return_value = "ANOMALY: HR^Heart Rate - Heart rate of 0 is clinically impossible"
    normalizer.aiHelper = ai_mock

    usecase = DefaultHealthCareUsecase(
        decoder=router, validator=validator, normalizer=normalizer, storage=storage
    )

    controller = RestController()

    @controller.app.exception_handler(RequestValidationError)
    async def _val_err(request, exc):
        return JSONResponse(status_code=422, content={"type": "about:blank", "title": "Unprocessable Content", "status": 422, "detail": str(exc)})

    controller.add_endpoint("/messages", "POST", create_process_message_handler(usecase))
    client = TestClient(controller.app, raise_server_exceptions=False)

    resp = client.post("/messages", json={"protocol": "hl7v2", "raw_payload": VALID_HL7_WITH_OBX})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == STATUS_STORED
    assert len(body["warnings"]) > 0
