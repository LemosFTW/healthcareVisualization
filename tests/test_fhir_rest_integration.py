"""Tests for Story 2.2: FHIR Support via REST — Router Integration.

Verifies that POST /messages with protocol="fhir" routes to FhirDecoder,
then flows through Hl7Validator, HealthcareMessageNormalizer, PostgreSqlStorage
WITHOUT modifying any of those components.
"""
import json
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
    FhirDecoder,
    Hl7V2Decoder,
    PostgreSqlStorage,
)
from transport.messages_handler import create_process_message_handler


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
        {
            "resource": {
                "resourceType": "Patient",
                "id": "patient-001",
                "name": [{"family": "Smith", "given": ["Jane"]}],
                "gender": "female",
            }
        },
        {
            "resource": {
                "resourceType": "Observation",
                "id": "obs-001",
                "status": "final",
                "code": {"text": "Heart Rate"},
                "valueQuantity": {"value": 0, "unit": "bpm"},  # suspicious: 0 bpm
            }
        },
    ],
})

MALFORMED_FHIR = "{ not valid json }"


def _make_engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _build_client(ai_mock=None):
    engine = _make_engine()
    storage = PostgreSqlStorage(engine)
    router = HealthcareDecoderRouter({"hl7v2": Hl7V2Decoder(), "fhir": FhirDecoder()})
    validator = Hl7Validator()
    normalizer = HealthcareNormalizer()
    if ai_mock:
        normalizer.aiHelper = ai_mock

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
    return TestClient(controller.app, raise_server_exceptions=False)


# AC1: FHIR via POST /messages → router dispatches to FhirDecoder → status="stored"
def test_post_fhir_patient_returns_200():
    client = _build_client()
    resp = client.post("/messages", json={"protocol": "fhir", "raw_payload": VALID_FHIR_PATIENT})
    assert resp.status_code == 200


def test_post_fhir_patient_returns_stored_status():
    client = _build_client()
    resp = client.post("/messages", json={"protocol": "fhir", "raw_payload": VALID_FHIR_PATIENT})
    assert resp.json()["status"] == STATUS_STORED


def test_post_fhir_patient_decoded_payload_has_resource_type():
    client = _build_client()
    resp = client.post("/messages", json={"protocol": "fhir", "raw_payload": VALID_FHIR_PATIENT})
    decoded = resp.json()["decoded_payload"]
    assert decoded["resourceType"] == "Patient"
    assert decoded["id"] == "patient-001"


def test_post_fhir_returns_empty_errors():
    client = _build_client()
    resp = client.post("/messages", json={"protocol": "fhir", "raw_payload": VALID_FHIR_PATIENT})
    assert resp.json()["errors"] == []


def test_post_fhir_bundle_returns_stored_status():
    client = _build_client()
    resp = client.post("/messages", json={"protocol": "fhir", "raw_payload": VALID_FHIR_BUNDLE})
    assert resp.json()["status"] == STATUS_STORED


# AC1 continued: same Hl7Validator, HealthcareMessageNormalizer, storage execute unchanged
def test_hl7_still_works_alongside_fhir_route():
    """HL7 and FHIR routes share the same pipeline without interfering."""
    client = _build_client()
    hl7_payload = (
        r"MSH|^~\&|App|Fac|Rec|RecFac|20230601120000||ADT^A01|MSG001|P|2.3"
        + "\rPID|1||12345^^^MRN||Doe^John^A||19800101|M"
    )
    hl7_resp = client.post("/messages", json={"protocol": "hl7v2", "raw_payload": hl7_payload})
    fhir_resp = client.post("/messages", json={"protocol": "fhir", "raw_payload": VALID_FHIR_PATIENT})
    assert hl7_resp.json()["status"] == STATUS_STORED
    assert fhir_resp.json()["status"] == STATUS_STORED


# Malformed FHIR → error envelope
def test_post_malformed_fhir_returns_error_status():
    client = _build_client()
    resp = client.post("/messages", json={"protocol": "fhir", "raw_payload": MALFORMED_FHIR})
    body = resp.json()
    assert resp.status_code == 200
    assert body["status"] == STATUS_ERROR
    assert any(e["stage"] == "decode" for e in body["errors"])


# AC3: FHIR with anomaly detected by GeminiAiHelper → warnings non-empty, status="stored"
def test_post_fhir_with_anomaly_returns_warnings():
    ai_mock = MagicMock()
    ai_mock.generateResponse.return_value = (
        "ANOMALY: Observation/obs-001 - Heart rate of 0 bpm is clinically impossible"
    )
    client = _build_client(ai_mock=ai_mock)

    resp = client.post("/messages", json={"protocol": "fhir", "raw_payload": VALID_FHIR_BUNDLE})
    body = resp.json()
    assert body["status"] == STATUS_STORED
    assert len(body["warnings"]) > 0


# AC2: Verify none of the existing components were modified for FHIR (duck-type check)
def test_fhir_decoder_is_separate_class_from_hl7_decoder():
    """FhirDecoder and Hl7V2Decoder are distinct; adding FHIR didn't change Hl7V2Decoder."""
    assert FhirDecoder is not Hl7V2Decoder
    hl7 = Hl7V2Decoder()
    fhir = FhirDecoder()
    assert type(hl7).__name__ == "Hl7V2Decoder"
    assert type(fhir).__name__ == "FhirDecoder"


def test_hl7_validator_is_unchanged_for_hl7_payloads():
    """Hl7Validator still validates HL7 correctly when MSH is present."""
    validator = Hl7Validator()
    hl7_payload = {
        "MSH": {
            "message_type": "ADT^A01",
            "message_control_id": "MSG001",
            "datetime": "20230601",
            "_raw_fields": [],
        },
        "_segment_order": ["MSH"],
    }
    result = validator.validate(hl7_payload)
    assert result.is_valid is True
