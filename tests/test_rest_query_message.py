"""Tests for Story 1.9: GET /messages/{id} — Query Message endpoint."""
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

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
from transport.messages_handler import (
    create_process_message_handler,
    create_query_message_handler,
)


VALID_HL7 = (
    r"MSH|^~\&|SendApp|SendFac|RecApp|RecFac|20230601120000||ADT^A01|MSG001|P|2.3"
    + "\rPID|1||12345^^^MRN||Doe^John^A||19800101|M"
)

MALFORMED_HL7 = "GARBAGE"


def _make_engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _build_client():
    """Build a TestClient wired to SQLite in-memory with both POST + GET endpoints."""
    engine = _make_engine()
    storage = PostgreSqlStorage(engine)
    router = HealthcareDecoderRouter({"hl7v2": Hl7V2Decoder()})
    validator = Hl7Validator()
    normalizer = HealthcareNormalizer()

    usecase = DefaultHealthCareUsecase(
        decoder=router, validator=validator, normalizer=normalizer, storage=storage
    )

    controller = RestController()

    @controller.app.exception_handler(RequestValidationError)
    async def _val_err(request, exc):
        return JSONResponse(
            status_code=422,
            content={"type": "about:blank", "title": "Unprocessable Content", "status": 422, "detail": str(exc)},
        )

    controller.add_endpoint("/messages", "POST", create_process_message_handler(usecase))
    controller.add_endpoint("/messages/{id}", "GET", create_query_message_handler(storage))

    return TestClient(controller.app, raise_server_exceptions=False)


# AC1: Existing ID → HTTP 200 with full stored MessageEnvelope
def test_get_existing_message_returns_200():
    client = _build_client()
    post_resp = client.post("/messages", json={"protocol": "hl7v2", "raw_payload": VALID_HL7, "id": "msg-get-001"})
    assert post_resp.status_code == 200

    get_resp = client.get("/messages/msg-get-001")
    assert get_resp.status_code == 200


def test_get_existing_message_contains_id():
    client = _build_client()
    client.post("/messages", json={"protocol": "hl7v2", "raw_payload": VALID_HL7, "id": "msg-get-002"})
    body = client.get("/messages/msg-get-002").json()
    assert body["id"] == "msg-get-002"


def test_get_existing_message_contains_status():
    client = _build_client()
    client.post("/messages", json={"protocol": "hl7v2", "raw_payload": VALID_HL7, "id": "msg-get-003"})
    body = client.get("/messages/msg-get-003").json()
    assert body["status"] == STATUS_STORED


def test_get_existing_message_contains_decoded_payload():
    client = _build_client()
    client.post("/messages", json={"protocol": "hl7v2", "raw_payload": VALID_HL7, "id": "msg-get-004"})
    body = client.get("/messages/msg-get-004").json()
    assert "decoded_payload" in body
    assert body["decoded_payload"] is not None


def test_get_existing_message_contains_normalized_payload():
    client = _build_client()
    client.post("/messages", json={"protocol": "hl7v2", "raw_payload": VALID_HL7, "id": "msg-get-005"})
    body = client.get("/messages/msg-get-005").json()
    assert "normalized_payload" in body
    assert body["normalized_payload"] is not None


def test_get_existing_message_contains_warnings_and_errors():
    client = _build_client()
    client.post("/messages", json={"protocol": "hl7v2", "raw_payload": VALID_HL7, "id": "msg-get-006"})
    body = client.get("/messages/msg-get-006").json()
    assert "warnings" in body
    assert "errors" in body
    assert isinstance(body["warnings"], list)
    assert isinstance(body["errors"], list)


def test_get_error_envelope_preserves_errors():
    client = _build_client()
    client.post("/messages", json={"protocol": "hl7v2", "raw_payload": MALFORMED_HL7, "id": "msg-err-001"})
    body = client.get("/messages/msg-err-001").json()
    assert body["status"] == STATUS_ERROR
    assert len(body["errors"]) >= 1
    assert body["errors"][0]["stage"] == "decode"


# AC2: Non-existent ID → HTTP 404 RFC 9457 Problem Details
def test_get_nonexistent_id_returns_404():
    client = _build_client()
    resp = client.get("/messages/does-not-exist")
    assert resp.status_code == 404


def test_get_404_response_is_rfc9457():
    client = _build_client()
    resp = client.get("/messages/no-such-id")
    body = resp.json()
    assert body["type"] == "about:blank"
    assert body["status"] == 404
    assert "title" in body
    assert "detail" in body
    assert "no-such-id" in body["detail"]
