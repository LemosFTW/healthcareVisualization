"""Tests for Story 1.4: Hl7Validator."""
import pytest
from healthcare_sdk.contracts import ErrorDetail, ValidationResult
from infrastructure.hl7_validator import Hl7Validator


# Minimal valid decoded payload (output from Hl7V2Decoder)
VALID_PAYLOAD = {
    "MSH": {
        "encoding_characters": r"^~\&",
        "sending_application": "SendApp",
        "sending_facility": "SendFac",
        "receiving_application": "RecApp",
        "receiving_facility": "RecFac",
        "datetime": "20230601120000",
        "security": "",
        "message_type": "ADT^A01",
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
    "_segment_order": ["MSH", "PID"],
}


def test_valid_payload_returns_is_valid_true():
    validator = Hl7Validator()
    result = validator.validate(VALID_PAYLOAD)
    assert isinstance(result, ValidationResult)
    assert result.is_valid is True
    assert result.errors == []


def test_missing_msh_returns_is_valid_false():
    payload = {"PID": VALID_PAYLOAD["PID"], "_segment_order": ["PID"]}
    validator = Hl7Validator()
    result = validator.validate(payload)
    assert result.is_valid is False
    assert any(e.code == "missing_segment" for e in result.errors)


def test_missing_message_type_returns_error():
    import copy
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["MSH"]["message_type"] = ""
    validator = Hl7Validator()
    result = validator.validate(payload)
    assert result.is_valid is False
    assert any(
        e.code == "missing_required_field" and e.context.get("field") == "message_type"
        for e in result.errors
    )


def test_missing_message_control_id_returns_error():
    import copy
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["MSH"]["message_control_id"] = ""
    validator = Hl7Validator()
    result = validator.validate(payload)
    assert result.is_valid is False
    assert any(e.context.get("field") == "message_control_id" for e in result.errors)


def test_missing_datetime_returns_error():
    import copy
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["MSH"]["datetime"] = "   "
    validator = Hl7Validator()
    result = validator.validate(payload)
    assert result.is_valid is False
    assert any(e.context.get("field") == "datetime" for e in result.errors)


def test_missing_patient_name_returns_error():
    import copy
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["PID"]["patient_name"] = ""
    validator = Hl7Validator()
    result = validator.validate(payload)
    assert result.is_valid is False
    assert any(e.context.get("field") == "patient_name" for e in result.errors)


def test_missing_all_patient_identifiers_returns_error():
    import copy
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["PID"]["patient_id"] = ""
    payload["PID"]["patient_identifier_list"] = ""
    validator = Hl7Validator()
    result = validator.validate(payload)
    assert result.is_valid is False
    assert any(e.code == "missing_patient_identifier" for e in result.errors)


def test_patient_id_field_alone_satisfies_identifier_check():
    import copy
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["PID"]["patient_id"] = "99999"
    payload["PID"]["patient_identifier_list"] = ""
    validator = Hl7Validator()
    result = validator.validate(payload)
    # patient_id alone is sufficient
    patient_id_errors = [e for e in result.errors if e.code == "missing_patient_identifier"]
    assert len(patient_id_errors) == 0


def test_payload_without_pid_is_valid_if_msh_complete():
    """PID is validated only when present; messages without PID (e.g. ACK) should pass."""
    payload = {"MSH": VALID_PAYLOAD["MSH"], "_segment_order": ["MSH"]}
    validator = Hl7Validator()
    result = validator.validate(payload)
    assert result.is_valid is True
    assert result.errors == []


def test_non_dict_payload_returns_error():
    validator = Hl7Validator()
    result = validator.validate("not a dict")  # type: ignore[arg-type]
    assert result.is_valid is False
    assert any(e.code == "invalid_payload_type" for e in result.errors)


def test_errors_are_error_detail_instances():
    import copy
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["MSH"]["message_type"] = ""
    validator = Hl7Validator()
    result = validator.validate(payload)
    for err in result.errors:
        assert isinstance(err, ErrorDetail)
        assert err.code
        assert err.message
        assert err.stage == "validate"


def test_multiple_missing_fields_returns_multiple_errors():
    import copy
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["MSH"]["message_type"] = ""
    payload["MSH"]["message_control_id"] = ""
    payload["PID"]["patient_name"] = ""
    validator = Hl7Validator()
    result = validator.validate(payload)
    assert result.is_valid is False
    assert len(result.errors) >= 3
