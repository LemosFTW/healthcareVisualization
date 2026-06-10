"""Tests for Story 3.1: MllpConnector — MLLP framing, receive(), ACK, Adapter contract."""
import queue
import socket
import time
import threading
import unittest.mock as mock

import pytest
from healthcare_sdk import Adapter, RawMessage

from transport.mllp_connector import MllpConnector, MLLP_START, MLLP_END


VALID_HL7 = (
    r"MSH|^~\&|SendApp|SendFac|RecApp|RecFac|20230601120000||ADT^A01|MSG001|P|2.3" + "\r"
    "PID|1||12345^^^MRN||Doe^John^A||19800101|M"
).encode("latin-1")


def _get_free_port() -> int:
    """Ask the OS for an available ephemeral port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _send_mllp(host: str, port: int, payload: bytes, timeout: float = 3.0) -> bytes:
    """Connect and send one MLLP-framed message, then read back the ACK."""
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


# AC3: Adapter contract
def test_mllp_connector_implements_adapter():
    connector = MllpConnector()
    assert isinstance(connector, Adapter)


def test_mllp_connector_has_execute_server_method():
    connector = MllpConnector()
    assert callable(getattr(connector, "executeServer", None))


def test_mllp_connector_has_receive_method():
    connector = MllpConnector()
    assert callable(getattr(connector, "receive", None))


# Unit tests: _parse_hl7
def test_parse_hl7_returns_raw_message():
    connector = MllpConnector()
    result = connector._parse_hl7(VALID_HL7)
    assert isinstance(result, RawMessage)


def test_parse_hl7_sets_protocol():
    connector = MllpConnector()
    result = connector._parse_hl7(VALID_HL7)
    assert result.protocol.lower() == "hl7v2"


def test_parse_hl7_sets_raw_payload():
    connector = MllpConnector()
    result = connector._parse_hl7(VALID_HL7)
    assert "MSH" in result.raw_payload


def test_parse_hl7_extracts_message_type():
    connector = MllpConnector()
    result = connector._parse_hl7(VALID_HL7)
    assert result.message_type == "ADT"


def test_parse_hl7_sets_source_metadata():
    connector = MllpConnector()
    result = connector._parse_hl7(VALID_HL7)
    assert result.metadata.get("source") == "mllp"


# Unit tests: _build_ack
def test_build_ack_returns_bytes():
    connector = MllpConnector()
    ack = connector._build_ack(VALID_HL7, "test-id")
    assert isinstance(ack, bytes)


def test_build_ack_contains_msh_segment():
    connector = MllpConnector()
    ack = connector._build_ack(VALID_HL7, "test-id")
    assert b"MSH" in ack


def test_build_ack_contains_msa_aa():
    connector = MllpConnector()
    ack = connector._build_ack(VALID_HL7, "test-id")
    assert b"MSA|AA" in ack


# Unit test: receive() returns from queue
def test_receive_returns_enqueued_message():
    connector = MllpConnector()
    raw = connector._parse_hl7(VALID_HL7)
    connector._message_queue.put(raw)
    result = connector.receive()
    assert result is raw


# AC1 + AC2: Integration test — real socket, real MLLP framing, real ACK
def test_mllp_integration_receive_and_ack():
    port = _get_free_port()
    connector = MllpConnector(host="127.0.0.1", port=port)
    connector.start_in_background()

    # Give server time to start
    for _ in range(20):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.1).close()
            break
        except OSError:
            time.sleep(0.05)

    try:
        # AC2: client sends MLLP-framed HL7 → server sends ACK back
        response = _send_mllp("127.0.0.1", port, VALID_HL7)

        # AC1: receive() returns RawMessage
        msg = connector.receive()
        assert isinstance(msg, RawMessage)
        assert msg.protocol.lower() == "hl7v2"
        assert "MSH" in msg.raw_payload

        # AC2: ACK was sent back (MLLP-framed, contains MSA|AA)
        assert MLLP_START in response
        assert b"MSA|AA" in response
    finally:
        connector.stop()
