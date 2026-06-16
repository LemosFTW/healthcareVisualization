"""Story 3.1 — MllpConnector: MLLP framing, receive(), ACK, Adapter contract."""
import socket
import time

import pytest
from healthcare_sdk import Adapter, RawMessage

from transport.mllp_connector import MLLP_END, MLLP_START, MllpConnector

VALID_HL7 = (
    r"MSH|^~\&|SendApp|SendFac|RecApp|RecFac|20230601120000||ADT^A01|MSG001|P|2.3" + "\r"
    "PID|1||12345^^^MRN||Doe^John^A||19800101|M"
).encode("latin-1")


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _send_mllp(host: str, port: int, payload: bytes, timeout: float = 3.0) -> bytes:
    with socket.create_connection((host, port), timeout=timeout) as s:
        s.sendall(MLLP_START + payload + MLLP_END)
        s.settimeout(timeout)
        response = b""
        while True:
            try:
                chunk = s.recv(4096)
                if not chunk:
                    break
                response += chunk
                if MLLP_END in response:
                    break
            except socket.timeout:
                break
    return response


@pytest.mark.p0
def test_mllp_connector_implements_adapter():
    """
    Given a MllpConnector instance
    When isinstance check is performed against the Adapter base class
    Then it must pass, confirming the SDK contract is satisfied
    """
    assert isinstance(MllpConnector(), Adapter)


@pytest.mark.p0
def test_mllp_connector_has_execute_server_method():
    """
    Given a MllpConnector instance
    When checking for the executeServer method
    Then it must exist and be callable
    """
    assert callable(getattr(MllpConnector(), "executeServer", None))


@pytest.mark.p0
def test_mllp_connector_has_receive_method():
    """
    Given a MllpConnector instance
    When checking for the receive method
    Then it must exist and be callable
    """
    assert callable(getattr(MllpConnector(), "receive", None))


@pytest.mark.p0
def test_parse_hl7_returns_raw_message():
    """
    Given a valid HL7v2 bytes payload
    When _parse_hl7() is called
    Then the result must be a RawMessage instance
    """
    connector = MllpConnector()
    assert isinstance(connector._parse_hl7(VALID_HL7), RawMessage)


@pytest.mark.p0
def test_parse_hl7_sets_protocol():
    """
    Given a valid HL7v2 bytes payload
    When _parse_hl7() is called
    Then the resulting RawMessage must have protocol='hl7v2'
    """
    connector = MllpConnector()
    assert connector._parse_hl7(VALID_HL7).protocol.lower() == "hl7v2"


@pytest.mark.p0
def test_parse_hl7_sets_raw_payload():
    """
    Given a valid HL7v2 bytes payload
    When _parse_hl7() is called
    Then the resulting RawMessage raw_payload must contain 'MSH'
    """
    connector = MllpConnector()
    assert "MSH" in connector._parse_hl7(VALID_HL7).raw_payload


@pytest.mark.p0
def test_parse_hl7_extracts_message_type():
    """
    Given a valid HL7v2 ADT^A01 message
    When _parse_hl7() is called
    Then the resulting RawMessage message_type must be 'ADT'
    """
    connector = MllpConnector()
    assert connector._parse_hl7(VALID_HL7).message_type == "ADT"


@pytest.mark.p0
def test_parse_hl7_sets_source_metadata():
    """
    Given a valid HL7v2 bytes payload
    When _parse_hl7() is called
    Then the resulting RawMessage metadata must have source='mllp'
    """
    connector = MllpConnector()
    assert connector._parse_hl7(VALID_HL7).metadata.get("source") == "mllp"


@pytest.mark.p0
def test_build_ack_returns_bytes():
    """
    Given a valid HL7v2 bytes payload and a message id
    When _build_ack() is called
    Then the result must be bytes
    """
    connector = MllpConnector()
    assert isinstance(connector._build_ack(VALID_HL7, "test-id"), bytes)


@pytest.mark.p0
def test_build_ack_contains_msh_segment():
    """
    Given a valid HL7v2 bytes payload
    When _build_ack() is called
    Then the ACK bytes must contain b'MSH'
    """
    connector = MllpConnector()
    assert b"MSH" in connector._build_ack(VALID_HL7, "test-id")


@pytest.mark.p0
def test_build_ack_contains_msa_aa():
    """
    Given a valid HL7v2 bytes payload
    When _build_ack() is called
    Then the ACK bytes must contain b'MSA|AA' indicating an Application Accept
    """
    connector = MllpConnector()
    assert b"MSA|AA" in connector._build_ack(VALID_HL7, "test-id")


@pytest.mark.p0
def test_receive_returns_enqueued_message():
    """
    Given a RawMessage manually placed into the internal queue
    When receive() is called
    Then the exact same RawMessage instance must be returned
    """
    connector = MllpConnector()
    raw = connector._parse_hl7(VALID_HL7)
    connector._message_queue.put(raw)
    assert connector.receive() is raw


@pytest.mark.p0
def test_mllp_integration_receive_and_ack():
    """
    Given a running MllpConnector server on a free port
    When a client sends one MLLP-framed HL7v2 message
    Then receive() must return a valid RawMessage and an MLLP-framed ACK with MSA|AA must be sent back
    """
    port = _get_free_port()
    connector = MllpConnector(host="127.0.0.1", port=port)
    connector.start_in_background()

    for _ in range(20):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
            break
        except OSError:
            time.sleep(0.05)

    try:
        response = _send_mllp("127.0.0.1", port, VALID_HL7)
        msg = connector.receive()
        assert isinstance(msg, RawMessage)
        assert msg.protocol.lower() == "hl7v2"
        assert "MSH" in msg.raw_payload
        assert MLLP_START in response
        assert b"MSA|AA" in response
    finally:
        connector.stop()
