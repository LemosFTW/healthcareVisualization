"""Story 2.1 — FhirDecoder."""
import json

import pytest
from healthcare_sdk import Decoder, RawMessage
from healthcare_sdk.errors import DecodeError

from infrastructure.decoders.fhir_decoder import FhirDecoder

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
    "entry": [{"resource": PATIENT}, {"resource": OBSERVATION}],
}


def _raw(payload, protocol: str = "fhir") -> RawMessage:
    if isinstance(payload, dict):
        payload = json.dumps(payload)
    return RawMessage(id="fhir-001", protocol=protocol, raw_payload=payload)


@pytest.mark.p0
def test_decode_patient_returns_dict_with_resource_type():
    """
    Given a valid FHIR Patient JSON payload
    When decode() is called
    Then the result must be a dict with resourceType='Patient'
    """
    decoder = FhirDecoder()
    result = decoder.decode(_raw(PATIENT))
    assert isinstance(result, dict)
    assert result["resourceType"] == "Patient"


@pytest.mark.p0
def test_decode_patient_returns_id():
    """
    Given a valid FHIR Patient JSON payload with id='patient-001'
    When decode() is called
    Then the result must contain id='patient-001'
    """
    decoder = FhirDecoder()
    result = decoder.decode(_raw(PATIENT))
    assert result["id"] == "patient-001"


@pytest.mark.p0
def test_decode_patient_returns_clinical_fields():
    """
    Given a valid FHIR Patient with gender, birthDate and name
    When decode() is called
    Then all three clinical fields must be present in the result
    """
    decoder = FhirDecoder()
    result = decoder.decode(_raw(PATIENT))
    assert result["gender"] == "male"
    assert result["birthDate"] == "1980-01-01"
    assert result["name"] == [{"family": "Doe", "given": ["John"]}]


@pytest.mark.p0
def test_decode_observation_returns_value():
    """
    Given a valid FHIR Observation with valueQuantity
    When decode() is called
    Then resourceType, status and valueQuantity must be present
    """
    decoder = FhirDecoder()
    result = decoder.decode(_raw(OBSERVATION))
    assert result["resourceType"] == "Observation"
    assert result["status"] == "final"
    assert result["valueQuantity"]["value"] == 72


@pytest.mark.p0
def test_decode_bundle_returns_resources_list():
    """
    Given a valid FHIR Bundle with two entries
    When decode() is called
    Then the result must have resourceType='Bundle' and a 'resources' list of length 2
    """
    decoder = FhirDecoder()
    result = decoder.decode(_raw(BUNDLE))
    assert result["resourceType"] == "Bundle"
    assert "resources" in result
    assert len(result["resources"]) == 2


@pytest.mark.p0
def test_decode_bundle_resources_contain_patient_and_observation():
    """
    Given a FHIR Bundle containing a Patient and an Observation
    When decode() is called
    Then the resources list must include both resource types
    """
    decoder = FhirDecoder()
    result = decoder.decode(_raw(BUNDLE))
    types = {r["resourceType"] for r in result["resources"]}
    assert "Patient" in types
    assert "Observation" in types


@pytest.mark.p0
def test_decode_handles_bytes_payload():
    """
    Given a RawMessage with a bytes-encoded FHIR JSON payload
    When decode() is called
    Then resourceType='Patient' must be parsed correctly
    """
    decoder = FhirDecoder()
    result = decoder.decode(_raw(json.dumps(PATIENT).encode("utf-8")))
    assert result["resourceType"] == "Patient"


@pytest.mark.p0
def test_malformed_json_raises_decode_error():
    """
    Given a payload that is not valid JSON
    When decode() is called
    Then DecodeError must be raised mentioning 'not valid JSON'
    """
    decoder = FhirDecoder()
    with pytest.raises(DecodeError, match="not valid JSON"):
        decoder.decode(_raw("{not: valid json}"))


@pytest.mark.p0
def test_empty_payload_raises_decode_error():
    """
    Given an empty string payload
    When decode() is called
    Then DecodeError must be raised mentioning 'empty'
    """
    decoder = FhirDecoder()
    with pytest.raises(DecodeError, match="empty"):
        decoder.decode(_raw(""))


@pytest.mark.p0
def test_missing_resource_type_raises_decode_error():
    """
    Given a valid JSON object missing the 'resourceType' key
    When decode() is called
    Then DecodeError must be raised mentioning 'resourceType'
    """
    decoder = FhirDecoder()
    with pytest.raises(DecodeError, match="resourceType"):
        decoder.decode(_raw({"id": "no-type", "name": "missing resourceType"}))


@pytest.mark.p0
def test_json_array_raises_decode_error():
    """
    Given a payload that is a JSON array instead of an object
    When decode() is called
    Then DecodeError must be raised mentioning 'JSON object'
    """
    decoder = FhirDecoder()
    with pytest.raises(DecodeError, match="JSON object"):
        decoder.decode(_raw("[1, 2, 3]"))


@pytest.mark.p0
def test_decode_signature_conforms_to_decoder_contract():
    """
    Given a FhirDecoder instance
    When isinstance check is performed against the Decoder base class
    Then it must pass, confirming the SDK contract is satisfied
    """
    decoder = FhirDecoder()
    assert isinstance(decoder, Decoder)
    result = decoder.decode(_raw(PATIENT))
    assert isinstance(result, dict)
