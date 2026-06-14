"""Story 1.4 — Hl7Validator."""
import copy
import pytest
from healthcare_sdk.contracts import ErrorDetail, ValidationResult
from infrastructure.validators.hl7_validator import Hl7Validator

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


@pytest.mark.p0
def test_valid_payload_returns_is_valid_true():
    """
    Given a decoded payload with all required MSH and PID fields
    When validate() is called
    Then ValidationResult must have is_valid=True and no errors
    """
    validator = Hl7Validator()
    result = validator.validate(VALID_PAYLOAD)
    assert isinstance(result, ValidationResult)
    assert result.is_valid is True
    assert result.errors == []


@pytest.mark.p0
def test_missing_msh_returns_is_valid_false():
    """
    Given a decoded payload missing the MSH segment
    When validate() is called
    Then is_valid must be False with a 'missing_segment' error
    """
    payload = {"PID": VALID_PAYLOAD["PID"], "_segment_order": ["PID"]}
    validator = Hl7Validator()
    result = validator.validate(payload)
    assert result.is_valid is False
    assert any(e.code == "missing_segment" for e in result.errors)


@pytest.mark.p0
def test_missing_message_type_returns_error():
    """
    Given a decoded payload with MSH.message_type set to empty string
    When validate() is called
    Then is_valid must be False with a 'missing_required_field' error for message_type
    """
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["MSH"]["message_type"] = ""
    validator = Hl7Validator()
    result = validator.validate(payload)
    assert result.is_valid is False
    assert any(
        e.code == "missing_required_field" and e.context.get("field") == "message_type"
        for e in result.errors
    )


@pytest.mark.p0
def test_missing_message_control_id_returns_error():
    """
    Given a decoded payload with MSH.message_control_id set to empty string
    When validate() is called
    Then is_valid must be False with an error for the message_control_id field
    """
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["MSH"]["message_control_id"] = ""
    validator = Hl7Validator()
    result = validator.validate(payload)
    assert result.is_valid is False
    assert any(e.context.get("field") == "message_control_id" for e in result.errors)


@pytest.mark.p0
def test_missing_datetime_returns_error():
    """
    Given a decoded payload with MSH.datetime set to whitespace
    When validate() is called
    Then is_valid must be False with an error for the datetime field
    """
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["MSH"]["datetime"] = "   "
    validator = Hl7Validator()
    result = validator.validate(payload)
    assert result.is_valid is False
    assert any(e.context.get("field") == "datetime" for e in result.errors)


@pytest.mark.p0
def test_missing_patient_name_returns_error():
    """
    Given a decoded payload with PID.patient_name set to empty string
    When validate() is called
    Then is_valid must be False with an error for the patient_name field
    """
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["PID"]["patient_name"] = ""
    validator = Hl7Validator()
    result = validator.validate(payload)
    assert result.is_valid is False
    assert any(e.context.get("field") == "patient_name" for e in result.errors)


@pytest.mark.p0
def test_missing_all_patient_identifiers_returns_error():
    """
    Given a decoded payload with both PID.patient_id and PID.patient_identifier_list empty
    When validate() is called
    Then is_valid must be False with a 'missing_patient_identifier' error
    """
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["PID"]["patient_id"] = ""
    payload["PID"]["patient_identifier_list"] = ""
    validator = Hl7Validator()
    result = validator.validate(payload)
    assert result.is_valid is False
    assert any(e.code == "missing_patient_identifier" for e in result.errors)


@pytest.mark.p0
def test_patient_id_field_alone_satisfies_identifier_check():
    """
    Given a decoded payload with only PID.patient_id populated (list empty)
    When validate() is called
    Then no missing_patient_identifier error must be present
    """
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["PID"]["patient_id"] = "99999"
    payload["PID"]["patient_identifier_list"] = ""
    validator = Hl7Validator()
    result = validator.validate(payload)
    patient_id_errors = [e for e in result.errors if e.code == "missing_patient_identifier"]
    assert len(patient_id_errors) == 0


@pytest.mark.p0
def test_payload_without_pid_is_valid_if_msh_complete():
    """
    Given a decoded payload with only MSH and no PID (e.g. an ACK message)
    When validate() is called
    Then is_valid must be True since PID is optional
    """
    payload = {"MSH": VALID_PAYLOAD["MSH"], "_segment_order": ["MSH"]}
    validator = Hl7Validator()
    result = validator.validate(payload)
    assert result.is_valid is True
    assert result.errors == []


@pytest.mark.p0
def test_non_dict_payload_returns_error():
    """
    Given a non-dict value passed as payload
    When validate() is called
    Then is_valid must be False with an 'invalid_payload_type' error
    """
    validator = Hl7Validator()
    result = validator.validate("not a dict")  # type: ignore[arg-type]
    assert result.is_valid is False
    assert any(e.code == "invalid_payload_type" for e in result.errors)


@pytest.mark.p0
def test_errors_are_error_detail_instances():
    """
    Given a decoded payload with a missing required field
    When validate() is called
    Then every error must be an ErrorDetail with code, message and stage='validate'
    """
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["MSH"]["message_type"] = ""
    validator = Hl7Validator()
    result = validator.validate(payload)
    for err in result.errors:
        assert isinstance(err, ErrorDetail)
        assert err.code
        assert err.message
        assert err.stage == "validate"


@pytest.mark.p0
def test_multiple_missing_fields_returns_multiple_errors():
    """
    Given a decoded payload with three required fields missing
    When validate() is called
    Then at least three errors must be returned
    """
    payload = copy.deepcopy(VALID_PAYLOAD)
    payload["MSH"]["message_type"] = ""
    payload["MSH"]["message_control_id"] = ""
    payload["PID"]["patient_name"] = ""
    validator = Hl7Validator()
    result = validator.validate(payload)
    assert result.is_valid is False
    assert len(result.errors) >= 3
