"""Tests for Story 1.5: HealthcareMessageNormalizer with anomaly detection."""
import pytest
from unittest.mock import MagicMock

from infrastructure.healthcare_normalizer import HealthcareMessageNormalizer
from healthcare_sdk.errors import NormalizationError


# Decoded payload matching Hl7V2Decoder output
DECODED_PAYLOAD = {
    "MSH": {
        "encoding_characters": r"^~\&",
        "sending_application": "LAB",
        "sending_facility": "HOSP",
        "receiving_application": "EHR",
        "receiving_facility": "CLINIC",
        "datetime": "20230601120000",
        "security": "",
        "message_type": "ORU^R01",
        "message_control_id": "MSG001",
        "processing_id": "P",
        "version_id": "2.3",
        "_raw_fields": [],
    },
    "PID": {
        "set_id": "1",
        "patient_id": "",
        "patient_identifier_list": "12345^^^MRN",
        "patient_name": "Doe^John^A",
        "date_of_birth": "19800101",
        "sex": "M",
        "_raw_fields": [],
    },
    "OBX": [
        {
            "set_id": "1",
            "value_type": "NM",
            "observation_identifier": "HR^Heart Rate",
            "observation_sub_id": "",
            "observation_value": "72",
            "units": "bpm",
            "reference_range": "60-100",
            "abnormal_flags": "N",
            "observation_result_status": "F",
            "_raw_fields": [],
        }
    ],
    "_segment_order": ["MSH", "PID", "OBX"],
}

PAYLOAD_WITH_SUSPICIOUS_HR = {
    **DECODED_PAYLOAD,
    "OBX": [
        {
            **DECODED_PAYLOAD["OBX"][0],
            "observation_value": "0",   # heart rate of 0 is clinically suspicious
            "abnormal_flags": "",
        }
    ],
}


def test_normalizeData_returns_dict():
    normalizer = HealthcareMessageNormalizer()
    result = normalizer.normalizeData(DECODED_PAYLOAD)
    assert isinstance(result, dict)


def test_normalized_contains_patient_block():
    normalizer = HealthcareMessageNormalizer()
    result = normalizer.normalizeData(DECODED_PAYLOAD)
    assert "patient" in result
    patient = result["patient"]
    assert patient["id"] == "12345^^^MRN"
    assert patient["name"] == "Doe^John^A"
    assert patient["date_of_birth"] == "19800101"
    assert patient["sex"] == "M"


def test_normalized_contains_identifiers_block():
    normalizer = HealthcareMessageNormalizer()
    result = normalizer.normalizeData(DECODED_PAYLOAD)
    assert "identifiers" in result
    ids = result["identifiers"]
    assert ids["message_control_id"] == "MSG001"
    assert ids["sending_application"] == "LAB"
    assert ids["sending_facility"] == "HOSP"


def test_normalized_contains_message_type_and_datetime():
    normalizer = HealthcareMessageNormalizer()
    result = normalizer.normalizeData(DECODED_PAYLOAD)
    assert result["message_type"] == "ORU^R01"
    assert result["datetime"] == "20230601120000"


def test_normalized_contains_clinical_observations():
    normalizer = HealthcareMessageNormalizer()
    result = normalizer.normalizeData(DECODED_PAYLOAD)
    assert "clinical_observations" in result
    obs = result["clinical_observations"]
    assert isinstance(obs, list)
    assert len(obs) == 1
    assert obs[0]["identifier"] == "HR^Heart Rate"
    assert obs[0]["value"] == "72"
    assert obs[0]["units"] == "bpm"


def test_no_ai_helper_returns_empty_warnings():
    normalizer = HealthcareMessageNormalizer()
    # aiHelper is None by default
    result = normalizer.normalizeData(DECODED_PAYLOAD)
    assert "warnings" in result
    assert result["warnings"] == []


def test_ai_helper_called_when_set():
    ai_mock = MagicMock()
    ai_mock.generateResponse.return_value = "NONE"

    normalizer = HealthcareMessageNormalizer()
    normalizer.aiHelper = ai_mock

    result = normalizer.normalizeData(DECODED_PAYLOAD)
    ai_mock.generateResponse.assert_called_once()
    assert result["warnings"] == []


def test_anomaly_detected_adds_warning():
    ai_mock = MagicMock()
    ai_mock.generateResponse.return_value = "ANOMALY: HR^Heart Rate - Heart rate of 0 is clinically impossible"

    normalizer = HealthcareMessageNormalizer()
    normalizer.aiHelper = ai_mock

    result = normalizer.normalizeData(PAYLOAD_WITH_SUSPICIOUS_HR)
    assert len(result["warnings"]) == 1
    assert "Heart Rate" in result["warnings"][0]


def test_multiple_anomalies_detected():
    ai_mock = MagicMock()
    ai_mock.generateResponse.return_value = (
        "ANOMALY: HR^Heart Rate - Heart rate of 0 is not viable\n"
        "ANOMALY: TEMP^Temperature - Temperature of 200 is incompatible with life"
    )

    normalizer = HealthcareMessageNormalizer()
    normalizer.aiHelper = ai_mock

    result = normalizer.normalizeData(DECODED_PAYLOAD)
    assert len(result["warnings"]) == 2


def test_ai_helper_exception_returns_empty_warnings():
    ai_mock = MagicMock()
    ai_mock.generateResponse.side_effect = RuntimeError("API down")

    normalizer = HealthcareMessageNormalizer()
    normalizer.aiHelper = ai_mock

    result = normalizer.normalizeData(DECODED_PAYLOAD)
    assert result["warnings"] == []


def test_non_dict_payload_raises_normalization_error():
    normalizer = HealthcareMessageNormalizer()
    with pytest.raises(NormalizationError):
        normalizer.normalizeData("not a dict")  # type: ignore[arg-type]


def test_payload_without_pid_still_normalizes():
    payload = {"MSH": DECODED_PAYLOAD["MSH"], "_segment_order": ["MSH"]}
    normalizer = HealthcareMessageNormalizer()
    result = normalizer.normalizeData(payload)
    assert result["patient"]["id"] == ""
    assert result["patient"]["name"] == ""
    assert result["clinical_observations"] == []
    assert result["warnings"] == []
