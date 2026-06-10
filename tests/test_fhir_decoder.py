"""Tests for Story 2.1: FhirDecoder."""
import json
import pytest
from healthcare_sdk import RawMessage
from healthcare_sdk.errors import DecodeError
from infrastructure.fhir_decoder import FhirDecoder


def _raw(payload, protocol: str = "fhir") -> RawMessage:
    if isinstance(payload, dict):
        payload = json.dumps(payload)
    return RawMessage(id="fhir-001", protocol=protocol, raw_payload=payload)


PATIENT = {
    "resourceType": "Patient",
    "id": "patient-001",
    "name": [{"family": "Doe", "given": ["John"]}],
    "gender": "male",
    "birthDate": "1980-01-01",
}

OBSERVATION = {
    "resourceType": "Observation",
    "id": "obs-001",
    "status": "final",
    "code": {"coding": [{"code": "8867-4", "display": "Heart rate"}]},
    "valueQuantity": {"value": 72, "unit": "bpm"},
}

BUNDLE = {
    "resourceType": "Bundle",
    "id": "bundle-001",
    "type": "message",
    "entry": [
        {"resource": PATIENT},
        {"resource": OBSERVATION},
    ],
}


# AC1: Valid FHIR JSON → structured dict with resourceType, id, clinical fields
def test_decode_patient_returns_dict_with_resource_type():
    decoder = FhirDecoder()
    result = decoder.decode(_raw(PATIENT))
    assert isinstance(result, dict)
    assert result["resourceType"] == "Patient"


def test_decode_patient_returns_id():
    decoder = FhirDecoder()
    result = decoder.decode(_raw(PATIENT))
    assert result["id"] == "patient-001"


def test_decode_patient_returns_clinical_fields():
    decoder = FhirDecoder()
    result = decoder.decode(_raw(PATIENT))
    assert result["gender"] == "male"
    assert result["birthDate"] == "1980-01-01"
    assert result["name"] == [{"family": "Doe", "given": ["John"]}]


def test_decode_observation_returns_value():
    decoder = FhirDecoder()
    result = decoder.decode(_raw(OBSERVATION))
    assert result["resourceType"] == "Observation"
    assert result["status"] == "final"
    assert result["valueQuantity"]["value"] == 72


def test_decode_bundle_returns_resources_list():
    decoder = FhirDecoder()
    result = decoder.decode(_raw(BUNDLE))
    assert result["resourceType"] == "Bundle"
    assert "resources" in result
    assert len(result["resources"]) == 2


def test_decode_bundle_resources_contain_patient_and_observation():
    decoder = FhirDecoder()
    result = decoder.decode(_raw(BUNDLE))
    types = {r["resourceType"] for r in result["resources"]}
    assert "Patient" in types
    assert "Observation" in types


def test_decode_handles_bytes_payload():
    decoder = FhirDecoder()
    result = decoder.decode(_raw(json.dumps(PATIENT).encode("utf-8")))
    assert result["resourceType"] == "Patient"


# AC2: Malformed / missing required fields → DecodeError with descriptive message
def test_malformed_json_raises_decode_error():
    decoder = FhirDecoder()
    with pytest.raises(DecodeError, match="not valid JSON"):
        decoder.decode(_raw("{not: valid json}"))


def test_empty_payload_raises_decode_error():
    decoder = FhirDecoder()
    with pytest.raises(DecodeError, match="empty"):
        decoder.decode(_raw(""))


def test_missing_resource_type_raises_decode_error():
    decoder = FhirDecoder()
    with pytest.raises(DecodeError, match="resourceType"):
        decoder.decode(_raw({"id": "no-type", "name": "missing resourceType"}))


def test_json_array_raises_decode_error():
    decoder = FhirDecoder()
    with pytest.raises(DecodeError, match="JSON object"):
        decoder.decode(_raw("[1, 2, 3]"))


# AC3: Signature conforms to Decoder contract
def test_decode_signature_returns_dict():
    from healthcare_sdk import Decoder
    decoder = FhirDecoder()
    assert isinstance(decoder, Decoder)
    result = decoder.decode(_raw(PATIENT))
    assert isinstance(result, dict)
