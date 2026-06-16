"""Story 1.8 — POST /messages REST endpoint."""
from unittest.mock import MagicMock

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
    HealthcareMessageNormalizer,
    Hl7V2Decoder,
    Hl7Validator,
)
from repositories import PostgreSqlStorage
from transport.messages_handler import create_process_message_handler
from usecases import ProcessMessageUsecase

VALID_HL7 = (
    r"MSH|^~\&|SendApp|SendFac|RecApp|RecFac|20230601120000||ADT^A01|MSG001|P|2.3"
    + "\rPID|1||12345^^^MRN||Doe^John^A||19800101|M"
)

VALID_HL7_WITH_OBX = (
    r"MSH|^~\&|LAB|HOSP|EHR|CLINIC|20230601120000||ORU^R01|MSG002|P|2.3"
    + "\rPID|1||99999^^^MRN||Smith^Jane||19900101|F"
    + "\rOBR|1|O001|F001|CBC^Complete Blood Count"
    + "\rOBX|1|NM|HR^Heart Rate||0|bpm|60-100|L||F"
)

MALFORMED_HL7 = "NOT_HL7_AT_ALL"


def _make_engine():
    return create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)


def _build_client(ai_mock=None):
    engine = _make_engine()
    storage = PostgreSqlStorage(engine)
    router = HealthcareDecoderRouter({"hl7v2": Hl7V2Decoder()})
    validator = Hl7Validator()
    normalizer = HealthcareMessageNormalizer()
    if ai_mock:
        normalizer.aiHelper = ai_mock

    usecase = ProcessMessageUsecase(decoder=router, validator=validator, normalizer=normalizer, storage=storage)
    controller = RestController()

    @controller.app.exception_handler(RequestValidationError)
    async def _val_err(request, exc):
        return JSONResponse(status_code=422, content={"type": "about:blank", "title": "Unprocessable Content", "status": 422, "detail": str(exc)})

    controller.add_endpoint("/messages", "POST", create_process_message_handler(usecase))
    return TestClient(controller.app, raise_server_exceptions=False)


@pytest.mark.p0
def test_post_valid_hl7_returns_200_with_stored_status():
    """
    Given a valid HL7v2 message payload
    When POST /messages is called
    Then HTTP 200 must be returned with status='stored'
    """
    client = _build_client()
    resp = client.post("/messages", json={"protocol": "hl7v2", "raw_payload": VALID_HL7})
    assert resp.status_code == 200
    assert resp.json()["status"] == STATUS_STORED


@pytest.mark.p0
def test_post_valid_hl7_response_contains_decoded_payload():
    """
    Given a valid HL7v2 message
    When POST /messages is called
    Then the response body must contain a non-null decoded_payload with MSH key
    """
    client = _build_client()
    resp = client.post("/messages", json={"protocol": "hl7v2", "raw_payload": VALID_HL7})
    body = resp.json()
    assert "decoded_payload" in body
    assert body["decoded_payload"] is not None
    assert "MSH" in body["decoded_payload"]


@pytest.mark.p0
def test_post_valid_hl7_response_contains_normalized_payload():
    """
    Given a valid HL7v2 message
    When POST /messages is called
    Then the response body must contain a non-null normalized_payload
    """
    client = _build_client()
    resp = client.post("/messages", json={"protocol": "hl7v2", "raw_payload": VALID_HL7})
    body = resp.json()
    assert "normalized_payload" in body
    assert body["normalized_payload"] is not None


@pytest.mark.p0
def test_post_valid_hl7_response_has_empty_errors():
    """
    Given a valid HL7v2 message
    When POST /messages is called
    Then the errors list in the response must be empty
    """
    client = _build_client()
    resp = client.post("/messages", json={"protocol": "hl7v2", "raw_payload": VALID_HL7})
    assert resp.json()["errors"] == []


@pytest.mark.p0
def test_post_valid_hl7_response_has_warnings_field():
    """
    Given a valid HL7v2 message processed without an AI helper
    When POST /messages is called
    Then the response must contain a 'warnings' list (empty since no AI helper)
    """
    client = _build_client()
    resp = client.post("/messages", json={"protocol": "hl7v2", "raw_payload": VALID_HL7})
    body = resp.json()
    assert "warnings" in body
    assert isinstance(body["warnings"], list)


@pytest.mark.p0
def test_post_malformed_hl7_returns_200_with_error_status():
    """
    Given a payload that is not valid HL7v2
    When POST /messages is called
    Then HTTP 200 must be returned with status='error'
    """
    client = _build_client()
    resp = client.post("/messages", json={"protocol": "hl7v2", "raw_payload": MALFORMED_HL7})
    assert resp.status_code == 200
    assert resp.json()["status"] == STATUS_ERROR


@pytest.mark.p0
def test_post_malformed_hl7_response_has_decode_error():
    """
    Given a malformed HL7v2 payload
    When POST /messages is called
    Then the errors list must contain at least one error with stage='decode'
    """
    client = _build_client()
    resp = client.post("/messages", json={"protocol": "hl7v2", "raw_payload": MALFORMED_HL7})
    body = resp.json()
    assert len(body["errors"]) >= 1
    assert "decode" in [e["stage"] for e in body["errors"]]


@pytest.mark.p0
def test_post_missing_protocol_returns_422():
    """
    Given a request body missing the 'protocol' field
    When POST /messages is called
    Then HTTP 422 must be returned
    """
    client = _build_client()
    assert client.post("/messages", json={"raw_payload": VALID_HL7}).status_code == 422


@pytest.mark.p0
def test_post_missing_raw_payload_returns_422():
    """
    Given a request body missing the 'raw_payload' field
    When POST /messages is called
    Then HTTP 422 must be returned
    """
    client = _build_client()
    assert client.post("/messages", json={"protocol": "hl7v2"}).status_code == 422


@pytest.mark.p0
def test_post_empty_body_returns_422():
    """
    Given an empty JSON object as the request body
    When POST /messages is called
    Then HTTP 422 must be returned
    """
    client = _build_client()
    assert client.post("/messages", json={}).status_code == 422


@pytest.mark.p0
def test_post_422_response_is_rfc9457_problem_details():
    """
    Given an invalid request body
    When POST /messages returns 422
    Then the response body must conform to RFC 9457 Problem Details format
    """
    client = _build_client()
    body = client.post("/messages", json={}).json()
    assert body["type"] == "about:blank"
    assert body["status"] == 422
    assert "title" in body
    assert "detail" in body


@pytest.mark.p0
def test_post_with_ai_helper_returns_warnings():
    """
    Given a normalizer with a mocked AI helper that detects an anomaly
    When POST /messages is called with a payload containing a suspicious observation
    Then the response must have status='stored' and non-empty warnings
    """
    ai_mock = MagicMock()
    ai_mock.generateResponse.return_value = "ANOMALY: HR^Heart Rate - Heart rate of 0 is clinically impossible"
    client = _build_client(ai_mock=ai_mock)
    resp = client.post("/messages", json={"protocol": "hl7v2", "raw_payload": VALID_HL7_WITH_OBX})
    body = resp.json()
    assert body["status"] == STATUS_STORED
    assert len(body["warnings"]) > 0
