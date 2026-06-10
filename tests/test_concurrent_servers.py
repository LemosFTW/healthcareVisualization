"""Tests for Story 3.3: Concurrent REST and MLLP Servers.

Verifies that both channels start on separate ports simultaneously,
process messages independently, and that failure in one channel
does not affect the other.
"""
import socket
import threading
import time

import pytest
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from healthcare_sdk import RestController
from healthcare_sdk.contracts import STATUS_STORED
from healthcare_sdk.usecases import DefaultHealthCareUsecase

from infrastructure import (
    FhirDecoder,
    HealthcareDecoderRouter,
    HealthcareNormalizer,
    Hl7Validator,
    Hl7V2Decoder,
    PostgreSqlStorage,
)
from transport import MllpConnector
from transport.messages_handler import create_process_message_handler, create_query_message_handler
from transport.mllp_pipeline import create_mllp_pipeline_loop
from transport.mllp_connector import MLLP_START, MLLP_END


VALID_HL7 = (
    r"MSH|^~\&|SendApp|SendFac|RecApp|RecFac|20230601120000||ADT^A01|MSG001|P|2.3"
    + "\rPID|1||12345^^^MRN||Doe^John^A||19800101|M"
).encode("latin-1")


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _make_engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def _build_system():
    """Build a minimal REST+MLLP system on a free test port."""
    engine = _make_engine()
    storage = PostgreSqlStorage(engine)
    router = HealthcareDecoderRouter({"hl7v2": Hl7V2Decoder(), "fhir": FhirDecoder()})
    validator = Hl7Validator()
    normalizer = HealthcareNormalizer()

    usecase = DefaultHealthCareUsecase(
        decoder=router, validator=validator, normalizer=normalizer, storage=storage
    )

    mllp_port = _get_free_port()
    mllp = MllpConnector(host="127.0.0.1", port=mllp_port)

    controller = RestController()

    @controller.app.exception_handler(RequestValidationError)
    async def _val_err(request, exc):
        return JSONResponse(
            status_code=422,
            content={"type": "about:blank", "title": "Unprocessable Content", "status": 422, "detail": str(exc)},
        )

    controller.add_endpoint("/messages", "POST", create_process_message_handler(usecase))
    controller.add_endpoint("/messages/{id}", "GET", create_query_message_handler(storage))

    return usecase, mllp, mllp_port, controller, storage


def _wait_for_port(host: str, port: int, timeout: float = 3.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            socket.create_connection((host, port), timeout=0.1).close()
            return True
        except OSError:
            time.sleep(0.05)
    return False


def _send_mllp(host: str, port: int, payload: bytes, timeout: float = 2.0) -> bytes:
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


# AC1: Both servers listen on separate ports simultaneously
def test_mllp_and_rest_both_accept_connections():
    """MLLP server binds its port while REST TestClient is active — no conflict."""
    usecase, mllp, mllp_port, controller, storage = _build_system()

    mllp.start_in_background()
    assert _wait_for_port("127.0.0.1", mllp_port), "MLLP port did not open in time"

    try:
        client = TestClient(controller.app, raise_server_exceptions=False)
        health = client.get("/health")
        assert health.status_code == 200
        assert _wait_for_port("127.0.0.1", mllp_port)
    finally:
        mllp.stop()


def test_rest_processes_while_mllp_server_is_running():
    """REST endpoint processes a message while MLLP server is active."""
    usecase, mllp, mllp_port, controller, storage = _build_system()

    mllp.start_in_background()
    pipeline_loop = create_mllp_pipeline_loop(mllp, usecase, storage)
    threading.Thread(target=pipeline_loop, daemon=True).start()
    _wait_for_port("127.0.0.1", mllp_port)

    try:
        client = TestClient(controller.app, raise_server_exceptions=False)
        resp = client.post(
            "/messages",
            json={"protocol": "hl7v2", "raw_payload": VALID_HL7.decode("latin-1")},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == STATUS_STORED
    finally:
        mllp.stop()


# AC2: Each message processed independently without interference
def test_mllp_and_rest_messages_processed_independently():
    """Both channels process messages concurrently without interfering."""
    usecase, mllp, mllp_port, controller, storage = _build_system()

    mllp.start_in_background()
    pipeline_loop = create_mllp_pipeline_loop(mllp, usecase, storage)
    threading.Thread(target=pipeline_loop, daemon=True).start()
    _wait_for_port("127.0.0.1", mllp_port)

    client = TestClient(controller.app, raise_server_exceptions=False)
    errors = []

    def _send_rest():
        try:
            resp = client.post(
                "/messages",
                json={
                    "protocol": "hl7v2",
                    "raw_payload": VALID_HL7.decode("latin-1"),
                    "id": "rest-concurrent",
                },
            )
            if resp.json()["status"] != STATUS_STORED:
                errors.append(f"REST status={resp.json()['status']}")
        except Exception as exc:
            errors.append(f"REST error: {exc}")

    def _send_mllp_msg():
        try:
            ack = _send_mllp("127.0.0.1", mllp_port, VALID_HL7)
            if b"MSA|AA" not in ack:
                errors.append("MLLP ACK missing MSA|AA")
        except Exception as exc:
            errors.append(f"MLLP error: {exc}")

    try:
        t1 = threading.Thread(target=_send_rest)
        t2 = threading.Thread(target=_send_mllp_msg)
        t1.start()
        t2.start()
        t1.join(timeout=5.0)
        t2.join(timeout=5.0)
        assert not errors, f"Concurrent channel errors: {errors}"
    finally:
        mllp.stop()


# AC2: MLLP failure does not affect REST
def test_mllp_failure_does_not_affect_rest():
    """Stopping the MLLP server does not interrupt REST processing."""
    usecase, mllp, mllp_port, controller, storage = _build_system()

    mllp.start_in_background()
    _wait_for_port("127.0.0.1", mllp_port)
    mllp.stop()  # simulate MLLP channel failure

    client = TestClient(controller.app, raise_server_exceptions=False)
    resp = client.post(
        "/messages",
        json={"protocol": "hl7v2", "raw_payload": VALID_HL7.decode("latin-1")},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == STATUS_STORED


# AC1: app.py main() architecture — structural test
def test_main_registers_both_channels():
    """app.py main() wires both MllpConnector and REST endpoint before serving."""
    import app as app_module
    import inspect

    main_src = inspect.getsource(app_module.main)

    assert "start_in_background" in main_src, "MLLP server not started in main()"
    assert "pipeline" in main_src, "MLLP pipeline not started in main()"
    assert "executeServer" in main_src, "REST server not started in main()"
    assert "add_endpoint" in main_src, "REST endpoints not registered in main()"
