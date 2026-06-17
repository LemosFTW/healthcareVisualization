"""Story 1.6 — HealthcareDecoderRouter."""

from unittest.mock import MagicMock

import pytest
from healthcare_sdk import RawMessage
from healthcare_sdk.errors import DecodeError

from infrastructure.decoder_router import HealthcareDecoderRouter

HL7_RESULT = {"MSH": {"message_type": "ADT^A01"}}
FHIR_RESULT = {"resourceType": "Patient"}


def _raw(protocol: str, payload: str = "test") -> RawMessage:
    return RawMessage(id="test-001", protocol=protocol, raw_payload=payload)


def _mock_decoder(return_value: dict):
    decoder = MagicMock()
    decoder.decode.return_value = return_value
    return decoder


@pytest.mark.p0
def test_routes_hl7v2_to_correct_decoder():
    """
    Given a router configured with an hl7v2 decoder
    When decode() is called with a RawMessage of protocol 'hl7v2'
    Then the hl7v2 decoder must be invoked and its result returned
    """
    hl7_decoder = _mock_decoder(HL7_RESULT)
    router = HealthcareDecoderRouter({"hl7v2": hl7_decoder})
    result = router.decode(_raw("hl7v2"))
    hl7_decoder.decode.assert_called_once()
    assert result == HL7_RESULT


@pytest.mark.p0
def test_routes_fhir_to_correct_decoder():
    """
    Given a router configured with a fhir decoder
    When decode() is called with a RawMessage of protocol 'fhir'
    Then the fhir decoder must be invoked and its result returned
    """
    fhir_decoder = _mock_decoder(FHIR_RESULT)
    router = HealthcareDecoderRouter({"fhir": fhir_decoder})
    result = router.decode(_raw("fhir"))
    fhir_decoder.decode.assert_called_once()
    assert result == FHIR_RESULT


@pytest.mark.p0
def test_protocol_matching_is_case_insensitive():
    """
    Given a router with a decoder registered under 'HL7V2'
    When decode() is called with protocol 'hl7v2' (lowercase) or 'HL7V2' (uppercase)
    Then both must route successfully to the same decoder
    """
    hl7_decoder = _mock_decoder(HL7_RESULT)
    router = HealthcareDecoderRouter({"HL7V2": hl7_decoder})
    assert router.decode(_raw("hl7v2")) == HL7_RESULT
    assert router.decode(_raw("HL7V2")) == HL7_RESULT


@pytest.mark.p0
def test_unknown_protocol_raises_decode_error():
    """
    Given a router with only an hl7v2 decoder
    When decode() is called with an unregistered protocol
    Then DecodeError must be raised naming the unknown protocol
    """
    router = HealthcareDecoderRouter({"hl7v2": _mock_decoder({})})
    with pytest.raises(DecodeError, match="unknown_protocol"):
        router.decode(_raw("unknown_protocol"))


@pytest.mark.p0
def test_decode_error_message_lists_supported_protocols():
    """
    Given a router with hl7v2 and fhir decoders
    When decode() is called with an unsupported protocol
    Then the DecodeError message must reference either the protocol or known protocols
    """
    router = HealthcareDecoderRouter(
        {"hl7v2": _mock_decoder({}), "fhir": _mock_decoder({})}
    )
    with pytest.raises(DecodeError) as exc_info:
        router.decode(_raw("dicom"))
    error_message = str(exc_info.value)
    assert "dicom" in error_message or "hl7v2" in error_message


@pytest.mark.p0
def test_empty_protocol_raises_decode_error():
    """
    Given a raw message with an empty protocol string
    When decode() is called
    Then DecodeError must be raised
    """
    router = HealthcareDecoderRouter({"hl7v2": _mock_decoder({})})
    with pytest.raises(DecodeError):
        router.decode(_raw(""))


@pytest.mark.p0
def test_register_adds_new_decoder():
    """
    Given a router initially configured with only hl7v2
    When register() is called to add a fhir decoder
    Then both protocols must route correctly
    """
    hl7_decoder = _mock_decoder(HL7_RESULT)
    fhir_decoder = _mock_decoder(FHIR_RESULT)
    router = HealthcareDecoderRouter({"hl7v2": hl7_decoder})
    router.register("fhir", fhir_decoder)
    assert router.decode(_raw("hl7v2")) == HL7_RESULT
    assert router.decode(_raw("fhir")) == FHIR_RESULT


@pytest.mark.p0
def test_router_delegates_raw_message_unchanged():
    """
    Given a router and an hl7v2 decoder mock
    When decode() is called
    Then the exact RawMessage instance must be passed to the decoder unchanged
    """
    raw = _raw("hl7v2", payload=r"MSH|^~\&|...")
    hl7_decoder = _mock_decoder(HL7_RESULT)
    router = HealthcareDecoderRouter({"hl7v2": hl7_decoder})
    router.decode(raw)
    hl7_decoder.decode.assert_called_once_with(raw)


@pytest.mark.p0
def test_router_returns_decoder_result_directly():
    """
    Given a decoder that returns a custom nested dict
    When the router calls decode()
    Then the exact same object reference must be returned
    """
    expected = {"custom": "result", "nested": {"a": 1}}
    router = HealthcareDecoderRouter({"hl7v2": _mock_decoder(expected)})
    result = router.decode(_raw("hl7v2"))
    assert result is expected
