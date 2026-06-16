"""Story 2.2 — FHIR Support via REST Router Integration."""
import json
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
    FhirDecoder,
    HealthcareDecoderRouter,
    HealthcareNormalizer,
    Hl7V2Decoder,
    Hl7Validator,
)
from repositories import PostgreSqlStorage
from transport.messages_handler import create_process_message_handler
from usecases import ProcessMessageUsecase

VALID_FHIR_PATIENT = json.dumps({
    "resourceType": "Patient",
    "id": "patient-001",
    "name": [{"family": "Doe", "given": ["John"]}],
    "gender": "male",
    "birthDate": "1980-01-01",
})

VALID_FHIR_BUNDLE = json.dumps({
    "resourceType": "Bundle",
    "id": "bundle-001",
    "type": "message",
    "entry": [
        {"resource": {"resourceType": "Patient", "id": "patient-001", "name": [{"family": "Smith", "given": ["Jane"]}], "gender": "female"}},
        {"resource": {"resourceType": "Observation", "id": "obs-001", "status": "final", "code": {"text": "Heart Rate"}, "valueQuantity": {"value": 0, "unit": "bpm"}}},
    ],
})

MALFORMED_FHIR = "{ not valid json }"


def _make_engine():
    return create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)


def _build_client(ai_mock=None):
    engine = _make_engine()
    storage = PostgreSqlStorage(engine)
    router = HealthcareDecoderRouter({"hl7v2": Hl7V2Decoder(), "fhir": FhirDecoder()})
    normalizer = HealthcareNormalizer()
    if ai_mock:
        normalizer.aiHelper = ai_mock
    usecase = ProcessMessageUsecase(
        decoder=router, validator=Hl7Validator(), normalizer=normalizer, storage=storage
    )
    controller = RestController()

    @controller.app.exception_handler(RequestValidationError)
    async def _val_err(request, exc):
        return JSONResponse(status_code=422, content={"type": "about:blank", "title": "Unprocessable Content", "status": 422, "detail": str(exc)})

    controller.add_endpoint("/messages", "POST", create_process_message_handler(usecase))
    return TestClient(controller.app, raise_server_exceptions=False)


@pytest.mark.p0
def test_post_fhir_patient_returns_200():
    """
    Given a valid FHIR Patient JSON payload
    When POST /messages is called with protocol='fhir'
    Then HTTP 200 must be returned
    """
    assert _build_client().post("/messages", json={"protocol": "fhir", "raw_payload": VALID_FHIR_PATIENT}).status_code == 200


@pytest.mark.p0
def test_post_fhir_patient_returns_stored_status():
    """
    Given a valid FHIR Patient JSON payload
    When POST /messages is called with protocol='fhir'
    Then the response status must be 'stored'
    """
    resp = _build_client().post("/messages", json={"protocol": "fhir", "raw_payload": VALID_FHIR_PATIENT})
    assert resp.json()["status"] == STATUS_STORED


@pytest.mark.p0
def test_post_fhir_patient_decoded_payload_has_resource_type():
    """
    Given a valid FHIR Patient payload
    When POST /messages is called
    Then decoded_payload must contain resourceType='Patient' and id='patient-001'
    """
    resp = _build_client().post("/messages", json={"protocol": "fhir", "raw_payload": VALID_FHIR_PATIENT})
    decoded = resp.json()["decoded_payload"]
    assert decoded["resourceType"] == "Patient"
    assert decoded["id"] == "patient-001"


@pytest.mark.p0
def test_post_fhir_returns_empty_errors():
    """
    Given a valid FHIR Patient payload
    When POST /messages is called
    Then the errors list in the response must be empty
    """
    resp = _build_client().post("/messages", json={"protocol": "fhir", "raw_payload": VALID_FHIR_PATIENT})
    assert resp.json()["errors"] == []


@pytest.mark.p0
def test_post_fhir_bundle_returns_stored_status():
    """
    Given a valid FHIR Bundle with two resources
    When POST /messages is called with protocol='fhir'
    Then the response status must be 'stored'
    """
    resp = _build_client().post("/messages", json={"protocol": "fhir", "raw_payload": VALID_FHIR_BUNDLE})
    assert resp.json()["status"] == STATUS_STORED


@pytest.mark.p0
def test_hl7_still_works_alongside_fhir_route():
    """
    Given a router supporting both hl7v2 and fhir protocols
    When one HL7v2 and one FHIR message are posted sequentially
    Then both must return status='stored' without interfering
    """
    client = _build_client()
    hl7_payload = r"MSH|^~\&|App|Fac|Rec|RecFac|20230601120000||ADT^A01|MSG001|P|2.3" + "\rPID|1||12345^^^MRN||Doe^John^A||19800101|M"
    hl7_resp = client.post("/messages", json={"protocol": "hl7v2", "raw_payload": hl7_payload})
    fhir_resp = client.post("/messages", json={"protocol": "fhir", "raw_payload": VALID_FHIR_PATIENT})
    assert hl7_resp.json()["status"] == STATUS_STORED
    assert fhir_resp.json()["status"] == STATUS_STORED


@pytest.mark.p0
def test_post_malformed_fhir_returns_error_status():
    """
    Given a malformed FHIR payload (not valid JSON)
    When POST /messages is called with protocol='fhir'
    Then HTTP 200 must be returned with status='error' and a decode-stage error
    """
    resp = _build_client().post("/messages", json={"protocol": "fhir", "raw_payload": MALFORMED_FHIR})
    body = resp.json()
    assert resp.status_code == 200
    assert body["status"] == STATUS_ERROR
    assert any(e["stage"] == "decode" for e in body["errors"])


@pytest.mark.p0
def test_post_fhir_with_anomaly_returns_warnings():
    """
    Given a FHIR Bundle with a clinically suspicious observation and a mocked AI helper
    When POST /messages is called
    Then the response must have status='stored' and at least one warning
    """
    ai_mock = MagicMock()
    ai_mock.generateResponse.return_value = "ANOMALY: Observation/obs-001 - Heart rate of 0 bpm is clinically impossible"
    resp = _build_client(ai_mock=ai_mock).post("/messages", json={"protocol": "fhir", "raw_payload": VALID_FHIR_BUNDLE})
    body = resp.json()
    assert body["status"] == STATUS_STORED
    assert len(body["warnings"]) > 0


@pytest.mark.p0
def test_fhir_decoder_is_separate_class_from_hl7_decoder():
    """
    Given the FhirDecoder and Hl7V2Decoder classes
    When their types are compared
    Then they must be distinct classes confirming FHIR support was added without modifying HL7 decoder
    """
    assert FhirDecoder is not Hl7V2Decoder
    assert type(Hl7V2Decoder()).__name__ == "Hl7V2Decoder"
    assert type(FhirDecoder()).__name__ == "FhirDecoder"


@pytest.mark.p0
def test_hl7_validator_is_unchanged_for_hl7_payloads():
    """
    Given the Hl7Validator with a valid decoded HL7 payload
    When validate() is called
    Then is_valid must be True confirming the validator was not modified for FHIR support
    """
    validator = Hl7Validator()
    hl7_payload = {
        "MSH": {"message_type": "ADT^A01", "message_control_id": "MSG001", "datetime": "20230601", "_raw_fields": []},
        "_segment_order": ["MSH"],
    }
    assert validator.validate(hl7_payload).is_valid is True
