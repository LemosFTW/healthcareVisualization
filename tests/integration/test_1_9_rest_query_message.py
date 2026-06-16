"""Story 1.9 — GET /messages/{id} endpoint."""
import pytest
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from healthcare_sdk import RestController
from healthcare_sdk.contracts import STATUS_ERROR, STATUS_STORED
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from infrastructure import (
    HealthcareDecoderRouter,
    HealthcareNormalizer,
    Hl7V2Decoder,
    Hl7Validator,
)
from repositories import PostgreSqlStorage
from transport.messages_handler import (
    create_process_message_handler,
    create_query_message_handler,
)
from usecases import ProcessMessageUsecase, QueryMessageUsecase

VALID_HL7 = (
    r"MSH|^~\&|SendApp|SendFac|RecApp|RecFac|20230601120000||ADT^A01|MSG001|P|2.3"
    + "\rPID|1||12345^^^MRN||Doe^John^A||19800101|M"
)
MALFORMED_HL7 = "GARBAGE"


def _make_engine():
    return create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)


def _build_client():
    engine = _make_engine()
    storage = PostgreSqlStorage(engine)
    router = HealthcareDecoderRouter({"hl7v2": Hl7V2Decoder()})
    process_usecase = ProcessMessageUsecase(
        decoder=router, validator=Hl7Validator(), normalizer=HealthcareNormalizer(), storage=storage
    )
    query_usecase = QueryMessageUsecase(storage=storage)
    controller = RestController()

    @controller.app.exception_handler(RequestValidationError)
    async def _val_err(request, exc):
        return JSONResponse(status_code=422, content={"type": "about:blank", "title": "Unprocessable Content", "status": 422, "detail": str(exc)})

    controller.add_endpoint("/messages", "POST", create_process_message_handler(process_usecase))
    controller.add_endpoint("/messages/{id}", "GET", create_query_message_handler(query_usecase))
    return TestClient(controller.app, raise_server_exceptions=False)


@pytest.mark.p0
def test_get_existing_message_returns_200():
    """
    Given a message previously stored via POST /messages with id='msg-get-001'
    When GET /messages/msg-get-001 is called
    Then HTTP 200 must be returned
    """
    client = _build_client()
    client.post("/messages", json={"protocol": "hl7v2", "raw_payload": VALID_HL7, "id": "msg-get-001"})
    assert client.get("/messages/msg-get-001").status_code == 200


@pytest.mark.p0
def test_get_existing_message_contains_id():
    """
    Given a stored message with id='msg-get-002'
    When GET /messages/msg-get-002 is called
    Then the response body must contain id='msg-get-002'
    """
    client = _build_client()
    client.post("/messages", json={"protocol": "hl7v2", "raw_payload": VALID_HL7, "id": "msg-get-002"})
    assert client.get("/messages/msg-get-002").json()["id"] == "msg-get-002"


@pytest.mark.p0
def test_get_existing_message_contains_status():
    """
    Given a valid HL7v2 message stored via POST
    When GET is called for that message
    Then the response status must be 'stored'
    """
    client = _build_client()
    client.post("/messages", json={"protocol": "hl7v2", "raw_payload": VALID_HL7, "id": "msg-get-003"})
    assert client.get("/messages/msg-get-003").json()["status"] == STATUS_STORED


@pytest.mark.p0
def test_get_existing_message_contains_decoded_payload():
    """
    Given a valid HL7v2 message stored via POST
    When GET is called for that message
    Then the response must contain a non-null decoded_payload
    """
    client = _build_client()
    client.post("/messages", json={"protocol": "hl7v2", "raw_payload": VALID_HL7, "id": "msg-get-004"})
    body = client.get("/messages/msg-get-004").json()
    assert "decoded_payload" in body
    assert body["decoded_payload"] is not None


@pytest.mark.p0
def test_get_existing_message_contains_normalized_payload():
    """
    Given a valid HL7v2 message stored via POST
    When GET is called for that message
    Then the response must contain a non-null normalized_payload
    """
    client = _build_client()
    client.post("/messages", json={"protocol": "hl7v2", "raw_payload": VALID_HL7, "id": "msg-get-005"})
    body = client.get("/messages/msg-get-005").json()
    assert "normalized_payload" in body
    assert body["normalized_payload"] is not None


@pytest.mark.p0
def test_get_existing_message_contains_warnings_and_errors():
    """
    Given a valid HL7v2 message stored via POST
    When GET is called for that message
    Then the response must include 'warnings' and 'errors' as lists
    """
    client = _build_client()
    client.post("/messages", json={"protocol": "hl7v2", "raw_payload": VALID_HL7, "id": "msg-get-006"})
    body = client.get("/messages/msg-get-006").json()
    assert isinstance(body.get("warnings"), list)
    assert isinstance(body.get("errors"), list)


@pytest.mark.p0
def test_get_error_envelope_preserves_errors():
    """
    Given a malformed HL7v2 message stored via POST (produces error envelope)
    When GET is called for that message
    Then status must be 'error' and errors[0].stage must be 'decode'
    """
    client = _build_client()
    client.post("/messages", json={"protocol": "hl7v2", "raw_payload": MALFORMED_HL7, "id": "msg-err-001"})
    body = client.get("/messages/msg-err-001").json()
    assert body["status"] == STATUS_ERROR
    assert len(body["errors"]) >= 1
    assert body["errors"][0]["stage"] == "decode"


@pytest.mark.p0
def test_get_nonexistent_id_returns_404():
    """
    Given no stored message with id='does-not-exist'
    When GET /messages/does-not-exist is called
    Then HTTP 404 must be returned
    """
    client = _build_client()
    assert client.get("/messages/does-not-exist").status_code == 404


@pytest.mark.p0
def test_get_404_response_is_rfc9457():
    """
    Given a non-existent message id
    When GET returns 404
    Then the response body must conform to RFC 9457 Problem Details format with id in detail
    """
    client = _build_client()
    body = client.get("/messages/no-such-id").json()
    assert body["type"] == "about:blank"
    assert body["status"] == 404
    assert "title" in body
    assert "no-such-id" in body["detail"]
