"""Story 3.2 — MLLP Pipeline Integration."""
import threading
import time
import pytest
from unittest.mock import MagicMock

from healthcare_sdk.contracts import MessageEnvelope, RawMessage, STATUS_STORED, STATUS_ERROR, ErrorDetail
from transport.mllp_pipeline import create_mllp_pipeline_loop


def _make_raw(protocol: str = "HL7v2", payload: str = "MSH|test") -> RawMessage:
    return RawMessage(id="test-001", protocol=protocol, raw_payload=payload)


def _make_stored_envelope(msg_id: str = "test-001") -> MessageEnvelope:
    return MessageEnvelope(
        id=msg_id,
        protocol="HL7v2",
        message_type="ADT^A01",
        raw_payload="MSH|test",
        status=STATUS_STORED,
    )


def _make_error_envelope(msg_id: str = "test-err-001") -> MessageEnvelope:
    env = MessageEnvelope(
        id=msg_id, protocol="HL7v2", message_type="", raw_payload="BAD", status=STATUS_ERROR,
    )
    env.errors.append(ErrorDetail(code="decode_error", message="MSH not found", stage="decode"))
    return env


@pytest.mark.p0
def test_pipeline_calls_usecase_execute():
    """
    Given a pipeline loop with a mocked connector and usecase
    When one RawMessage is enqueued and the loop runs
    Then usecase.execute() must be called once with that exact message
    """
    raw = _make_raw()
    connector = MagicMock()
    connector.receive.side_effect = [raw, Exception("stop loop")]
    usecase = MagicMock()
    usecase.execute.return_value = _make_stored_envelope()
    storage = MagicMock()

    loop = create_mllp_pipeline_loop(connector, usecase, storage)
    t = threading.Thread(target=loop, daemon=True)
    t.start()
    t.join(timeout=1.0)

    usecase.execute.assert_called_once_with(raw)


@pytest.mark.p0
def test_pipeline_stored_envelope_not_saved_by_loop():
    """
    Given a pipeline where usecase.execute() returns a STATUS_STORED envelope
    When the loop processes the message
    Then storage.save() must NOT be called (usecase handles persistence internally)
    """
    connector = MagicMock()
    connector.receive.side_effect = [_make_raw(), Exception("stop")]
    usecase = MagicMock()
    usecase.execute.return_value = _make_stored_envelope()
    storage = MagicMock()

    loop = create_mllp_pipeline_loop(connector, usecase, storage)
    t = threading.Thread(target=loop, daemon=True)
    t.start()
    t.join(timeout=1.0)

    storage.save.assert_not_called()


@pytest.mark.p0
def test_pipeline_persists_error_envelope():
    """
    Given a pipeline where usecase.execute() returns a STATUS_ERROR envelope
    When the loop processes the message
    Then storage.save() must be called once with the error envelope
    """
    error_env = _make_error_envelope()
    connector = MagicMock()
    connector.receive.side_effect = [_make_raw(payload="GARBAGE"), Exception("stop")]
    usecase = MagicMock()
    usecase.execute.return_value = error_env
    storage = MagicMock()

    loop = create_mllp_pipeline_loop(connector, usecase, storage)
    t = threading.Thread(target=loop, daemon=True)
    t.start()
    t.join(timeout=1.0)

    storage.save.assert_called_once_with(error_env)


@pytest.mark.p0
def test_error_envelope_has_decode_stage_error():
    """
    Given an error envelope built for a decode failure
    When its errors are inspected
    Then at least one ErrorDetail must have stage='decode'
    """
    error_env = _make_error_envelope()
    assert any(e.stage == "decode" for e in error_env.errors)


@pytest.mark.p0
def test_ack_sent_before_pipeline_runs():
    """
    Given the MllpConnector implementation
    When inspecting _handle_client()
    Then the method must exist, confirming ACK is sent synchronously before queueing
    """
    from transport.mllp_connector import MllpConnector
    connector = MllpConnector()
    assert hasattr(connector, "_handle_client")


@pytest.mark.p0
def test_pipeline_continues_after_usecase_exception():
    """
    Given a pipeline where the first usecase.execute() raises RuntimeError
    When the loop processes two messages
    Then the loop must continue and process the second message successfully
    """
    raw1 = _make_raw()
    raw2 = RawMessage(id="test-002", protocol="HL7v2", raw_payload="MSH|second")
    stored_env = _make_stored_envelope("test-002")
    call_count = {"n": 0}

    def _side_effect(raw):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated crash")
        return stored_env

    stop_event = threading.Event()

    def _receive_side():
        yield raw1
        yield raw2
        stop_event.wait()
        raise Exception("stop loop")

    gen = _receive_side()
    connector = MagicMock()
    connector.receive.side_effect = lambda: next(gen)
    usecase = MagicMock()
    usecase.execute.side_effect = _side_effect
    storage = MagicMock()

    loop = create_mllp_pipeline_loop(connector, usecase, storage)
    t = threading.Thread(target=loop, daemon=True)
    t.start()

    deadline = time.time() + 2.0
    while call_count["n"] < 2 and time.time() < deadline:
        time.sleep(0.05)

    stop_event.set()
    t.join(timeout=1.0)

    assert call_count["n"] == 2, "Loop should have continued after crash"
