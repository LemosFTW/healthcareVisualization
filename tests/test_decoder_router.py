"""Tests for Story 1.6: HealthcareDecoderRouter."""
import pytest
from unittest.mock import MagicMock

from healthcare_sdk import RawMessage
from healthcare_sdk.errors import DecodeError
from infrastructure.decoder_router import HealthcareDecoderRouter


def _raw(protocol: str, payload: str = "test") -> RawMessage:
    return RawMessage(id="test-001", protocol=protocol, raw_payload=payload)


def _mock_decoder(return_value: dict):
    decoder = MagicMock()
    decoder.decode.return_value = return_value
    return decoder


HL7_RESULT = {"MSH": {"message_type": "ADT^A01"}}
FHIR_RESULT = {"resourceType": "Patient"}


def test_routes_hl7v2_to_correct_decoder():
    hl7_decoder = _mock_decoder(HL7_RESULT)
    router = HealthcareDecoderRouter({"hl7v2": hl7_decoder})

    result = router.decode(_raw("hl7v2"))

    hl7_decoder.decode.assert_called_once()
    assert result == HL7_RESULT


def test_routes_fhir_to_correct_decoder():
    fhir_decoder = _mock_decoder(FHIR_RESULT)
    router = HealthcareDecoderRouter({"fhir": fhir_decoder})

    result = router.decode(_raw("fhir"))

    fhir_decoder.decode.assert_called_once()
    assert result == FHIR_RESULT


def test_protocol_matching_is_case_insensitive():
    hl7_decoder = _mock_decoder(HL7_RESULT)
    router = HealthcareDecoderRouter({"HL7V2": hl7_decoder})

    result = router.decode(_raw("hl7v2"))
    assert result == HL7_RESULT

    result2 = router.decode(_raw("HL7V2"))
    assert result2 == HL7_RESULT


def test_unknown_protocol_raises_decode_error():
    router = HealthcareDecoderRouter({"hl7v2": _mock_decoder({})})
    with pytest.raises(DecodeError, match="unknown_protocol"):
        router.decode(_raw("unknown_protocol"))


def test_decode_error_message_lists_supported_protocols():
    router = HealthcareDecoderRouter({"hl7v2": _mock_decoder({}), "fhir": _mock_decoder({})})
    with pytest.raises(DecodeError) as exc_info:
        router.decode(_raw("dicom"))
    error_message = str(exc_info.value)
    assert "dicom" in error_message or "hl7v2" in error_message


def test_empty_protocol_raises_decode_error():
    router = HealthcareDecoderRouter({"hl7v2": _mock_decoder({})})
    with pytest.raises(DecodeError):
        router.decode(_raw(""))


def test_register_adds_new_decoder_without_modifying_router():
    hl7_decoder = _mock_decoder(HL7_RESULT)
    fhir_decoder = _mock_decoder(FHIR_RESULT)

    router = HealthcareDecoderRouter({"hl7v2": hl7_decoder})
    # Register a new decoder after construction — no modification to routing logic
    router.register("fhir", fhir_decoder)

    result_hl7 = router.decode(_raw("hl7v2"))
    result_fhir = router.decode(_raw("fhir"))

    assert result_hl7 == HL7_RESULT
    assert result_fhir == FHIR_RESULT


def test_router_delegates_raw_message_unchanged():
    raw = _raw("hl7v2", payload=r"MSH|^~\&|...")
    hl7_decoder = _mock_decoder(HL7_RESULT)
    router = HealthcareDecoderRouter({"hl7v2": hl7_decoder})

    router.decode(raw)

    hl7_decoder.decode.assert_called_once_with(raw)


def test_router_returns_decoder_result_directly():
    expected = {"custom": "result", "nested": {"a": 1}}
    router = HealthcareDecoderRouter({"hl7v2": _mock_decoder(expected)})

    result = router.decode(_raw("hl7v2"))
    assert result is expected
