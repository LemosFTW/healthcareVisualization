"""Story 1.3 — Hl7V2Decoder."""
import pytest
from healthcare_sdk import RawMessage
from healthcare_sdk.errors import DecodeError
from infrastructure.decoders.hl7v2_decoder import Hl7V2Decoder

VALID_HL7 = (
    r"MSH|^~\&|SendApp|SendFac|RecApp|RecFac|20230601120000||ADT^A01|MSG001|P|2.3" + "\r"
    "PID|1||12345^^^MRN||Doe^John^A||19800101|M|||123 Main St^^Springfield^IL^62701\r"
    "OBR|1|ORD001|LAB001|CBC^Complete Blood Count|||20230601100000\r"
    "OBX|1|NM|WBC^White Blood Cell Count||7.5|10^3/uL|4.5-11.0|N||F\r"
    "OBX|2|NM|HGB^Hemoglobin||14.2|g/dL|13.5-17.5|N||F"
)

MULTI_OBX_HL7 = (
    r"MSH|^~\&|LAB|HOSP|EHR|CLINIC|20230601120000||ORU^R01|MSG002|P|2.3" + "\r"
    "PID|1||99999|||Smith^Jane|||F\r"
    "OBR|1|O001|F001|PANEL^Basic Panel\r"
    "OBX|1|NM|GLU^Glucose||95|mg/dL|70-110|N||F\r"
    "OBX|2|NM|BUN^Blood Urea Nitrogen||18|mg/dL|7-25|N||F\r"
    "OBX|3|NM|CREAT^Creatinine||0.9|mg/dL|0.6-1.2|N||F"
)


def _make_raw(payload, protocol: str = "hl7v2") -> RawMessage:
    return RawMessage(id="test-001", protocol=protocol, raw_payload=payload)


@pytest.mark.p0
def test_decode_returns_dict():
    """
    Given a valid HL7v2 raw message
    When decode() is called
    Then the result must be a dict
    """
    decoder = Hl7V2Decoder()
    result = decoder.decode(_make_raw(VALID_HL7))
    assert isinstance(result, dict)


@pytest.mark.p0
def test_decode_contains_msh_segment():
    """
    Given a valid HL7v2 raw message with an MSH segment
    When decode() is called
    Then the result dict must contain an 'MSH' key
    """
    decoder = Hl7V2Decoder()
    result = decoder.decode(_make_raw(VALID_HL7))
    assert "MSH" in result


@pytest.mark.p0
def test_msh_fields_are_structured():
    """
    Given a valid HL7v2 raw message
    When decode() is called
    Then the MSH segment must expose structured named fields
    """
    decoder = Hl7V2Decoder()
    result = decoder.decode(_make_raw(VALID_HL7))
    msh = result["MSH"]
    assert msh["sending_application"] == "SendApp"
    assert msh["sending_facility"] == "SendFac"
    assert msh["receiving_application"] == "RecApp"
    assert msh["message_type"] == "ADT^A01"
    assert msh["version_id"] == "2.3"


@pytest.mark.p0
def test_decode_contains_pid_segment():
    """
    Given a valid HL7v2 message with a PID segment
    When decode() is called
    Then the PID segment must be present with patient name, DOB and sex
    """
    decoder = Hl7V2Decoder()
    result = decoder.decode(_make_raw(VALID_HL7))
    assert "PID" in result
    pid = result["PID"]
    assert pid["patient_name"] == "Doe^John^A"
    assert pid["date_of_birth"] == "19800101"
    assert pid["sex"] == "M"


@pytest.mark.p0
def test_decode_contains_obr_segment():
    """
    Given a valid HL7v2 message with an OBR segment
    When decode() is called
    Then the OBR segment must be present as a list with universal_service_id
    """
    decoder = Hl7V2Decoder()
    result = decoder.decode(_make_raw(VALID_HL7))
    assert "OBR" in result
    obr_list = result["OBR"]
    assert isinstance(obr_list, list)
    assert len(obr_list) == 1
    assert obr_list[0]["universal_service_id"] == "CBC^Complete Blood Count"


@pytest.mark.p0
def test_decode_contains_multiple_obx_segments():
    """
    Given a valid HL7v2 message with two OBX segments
    When decode() is called
    Then both OBX segments must be returned in a list
    """
    decoder = Hl7V2Decoder()
    result = decoder.decode(_make_raw(VALID_HL7))
    assert "OBX" in result
    obx_list = result["OBX"]
    assert isinstance(obx_list, list)
    assert len(obx_list) == 2
    assert obx_list[0]["observation_identifier"] == "WBC^White Blood Cell Count"
    assert obx_list[1]["observation_identifier"] == "HGB^Hemoglobin"


@pytest.mark.p0
def test_decode_preserves_segment_order():
    """
    Given a valid HL7v2 message
    When decode() is called
    Then _segment_order must be present with MSH as the first segment
    """
    decoder = Hl7V2Decoder()
    result = decoder.decode(_make_raw(VALID_HL7))
    assert "_segment_order" in result
    assert result["_segment_order"][0] == "MSH"


@pytest.mark.p0
def test_decode_handles_bytes_payload():
    """
    Given a RawMessage with a bytes payload encoded in latin-1
    When decode() is called
    Then the MSH segment must be successfully parsed
    """
    decoder = Hl7V2Decoder()
    raw = _make_raw(VALID_HL7.encode("latin-1"))
    result = decoder.decode(raw)
    assert "MSH" in result


@pytest.mark.p0
def test_decode_handles_lf_line_endings():
    """
    Given a valid HL7v2 message using LF instead of CR as segment separator
    When decode() is called
    Then MSH and PID must still be parsed correctly
    """
    hl7_lf = VALID_HL7.replace("\r", "\n")
    decoder = Hl7V2Decoder()
    result = decoder.decode(_make_raw(hl7_lf))
    assert "MSH" in result
    assert "PID" in result


@pytest.mark.p0
def test_malformed_raises_decode_error_empty():
    """
    Given a raw message with only whitespace as payload
    When decode() is called
    Then DecodeError must be raised mentioning 'no segments'
    """
    decoder = Hl7V2Decoder()
    with pytest.raises(DecodeError, match="no segments"):
        decoder.decode(_make_raw("   "))


@pytest.mark.p0
def test_malformed_raises_decode_error_no_msh():
    """
    Given a raw message that starts with PID instead of MSH
    When decode() is called
    Then DecodeError must be raised mentioning 'MSH'
    """
    decoder = Hl7V2Decoder()
    with pytest.raises(DecodeError, match="MSH"):
        decoder.decode(_make_raw("PID|1||12345"))


@pytest.mark.p0
def test_malformed_raises_decode_error_msh_too_short():
    """
    Given a raw message with an MSH segment that has too few fields
    When decode() is called
    Then DecodeError must be raised mentioning 'too short'
    """
    decoder = Hl7V2Decoder()
    with pytest.raises(DecodeError, match="too short"):
        decoder.decode(_make_raw("MSH|"))
