"""Story 3.3 — Concurrent REST and MLLP Servers."""
import socket
import threading
import time

import pytest
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from healthcare_sdk import RestController
from healthcare_sdk.contracts import STATUS_STORED
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from infrastructure import (
    FhirDecoder,
    HealthcareDecoderRouter,
    HealthcareNormalizer,
    Hl7V2Decoder,
    Hl7Validator,
)
from repositories import PostgreSqlStorage
from transport import MllpConnector
from transport.messages_handler import (
    create_process_message_handler,
    create_query_message_handler,
)
from transport.mllp_connector import MLLP_END, MLLP_START
from transport.mllp_pipeline import create_mllp_pipeline_loop
from usecases import ProcessMessageUsecase, QueryMessageUsecase

VALID_HL7 = (
    r"MSH|^~\&|SendApp|SendFac|RecApp|RecFac|20230601120000||ADT^A01|MSG001|P|2.3"
    + "\rPID|1||12345^^^MRN||Doe^John^A||19800101|M"
).encode("latin-1")


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _make_engine():
    return create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)


def _build_system():
    engine = _make_engine()
    storage = PostgreSqlStorage(engine)
    router = HealthcareDecoderRouter({"hl7v2": Hl7V2Decoder(), "fhir": FhirDecoder()})
    process_usecase = ProcessMessageUsecase(
        decoder=router, validator=Hl7Validator(), normalizer=HealthcareNormalizer(), storage=storage
    )
    query_usecase = QueryMessageUsecase(storage=storage)
    mllp_port = _get_free_port()
    mllp = MllpConnector(host="127.0.0.1", port=mllp_port)
    controller = RestController()

    @controller.app.exception_handler(RequestValidationError)
    async def _val_err(request, exc):
        return JSONResponse(status_code=422, content={"type": "about:blank", "title": "Unprocessable Content", "status": 422, "detail": str(exc)})

    controller.add_endpoint("/messages", "POST", create_process_message_handler(process_usecase))
    controller.add_endpoint("/messages/{id}", "GET", create_query_message_handler(query_usecase))
    return process_usecase, mllp, mllp_port, controller


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


@pytest.mark.p0
def test_mllp_and_rest_both_accept_connections():
    """
    Given both the MLLP server and the REST controller running simultaneously
    When connections are made to each
    Then both must accept connections without port conflicts
    """
    process_usecase, mllp, mllp_port, controller = _build_system()
    mllp.start_in_background()
    assert _wait_for_port("127.0.0.1", mllp_port), "MLLP port did not open in time"
    try:
        client = TestClient(controller.app, raise_server_exceptions=False)
        assert client.get("/health").status_code == 200
        assert _wait_for_port("127.0.0.1", mllp_port)
    finally:
        mllp.stop()


@pytest.mark.p0
def test_rest_processes_while_mllp_server_is_running():
    """
    Given a running MLLP server and pipeline loop
    When POST /messages is called via the REST endpoint
    Then the message must be processed and returned with status='stored'
    """
    process_usecase, mllp, mllp_port, controller = _build_system()
    mllp.start_in_background()
    pipeline_loop = create_mllp_pipeline_loop(mllp, process_usecase)
    threading.Thread(target=pipeline_loop, daemon=True).start()
    _wait_for_port("127.0.0.1", mllp_port)
    try:
        client = TestClient(controller.app, raise_server_exceptions=False)
        resp = client.post("/messages", json={"protocol": "hl7v2", "raw_payload": VALID_HL7.decode("latin-1")})
        assert resp.status_code == 200
        assert resp.json()["status"] == STATUS_STORED
    finally:
        mllp.stop()


@pytest.mark.p0
def test_mllp_and_rest_messages_processed_independently():
    """
    Given both channels running concurrently
    When one message is sent via MLLP and another via REST simultaneously
    Then both must complete successfully without interfering with each other
    """
    process_usecase, mllp, mllp_port, controller = _build_system()
    mllp.start_in_background()
    pipeline_loop = create_mllp_pipeline_loop(mllp, process_usecase)
    threading.Thread(target=pipeline_loop, daemon=True).start()
    _wait_for_port("127.0.0.1", mllp_port)

    client = TestClient(controller.app, raise_server_exceptions=False)
    errors = []

    def _send_rest():
        try:
            resp = client.post("/messages", json={"protocol": "hl7v2", "raw_payload": VALID_HL7.decode("latin-1"), "id": "rest-concurrent"})
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
        t1.start(); t2.start()
        t1.join(timeout=5.0); t2.join(timeout=5.0)
        assert not errors, f"Concurrent channel errors: {errors}"
    finally:
        mllp.stop()


@pytest.mark.p0
def test_mllp_failure_does_not_affect_rest():
    """
    Given a running system where the MLLP server is then stopped
    When POST /messages is called via the REST endpoint after MLLP stops
    Then the REST endpoint must still process the message successfully
    """
    process_usecase, mllp, mllp_port, controller = _build_system()
    mllp.start_in_background()
    _wait_for_port("127.0.0.1", mllp_port)
    mllp.stop()

    client = TestClient(controller.app, raise_server_exceptions=False)
    resp = client.post("/messages", json={"protocol": "hl7v2", "raw_payload": VALID_HL7.decode("latin-1")})
    assert resp.status_code == 200
    assert resp.json()["status"] == STATUS_STORED


@pytest.mark.p0
def test_main_registers_both_channels():
    """
    Given the app module
    When inspecting main() and run_mllp_worker() source code
    Then main() must launch a multiprocessing.Process with run_mllp_worker, register REST endpoints and start the REST server;
    and run_mllp_worker() must start the MLLP server and pipeline
    """
    import inspect

    import app as app_module

    main_src = inspect.getsource(app_module.main)
    worker_src = inspect.getsource(app_module.run_mllp_worker)

    assert "multiprocessing.Process" in main_src, "MLLP worker not launched as Process in main()"
    assert "run_mllp_worker" in main_src, "run_mllp_worker not referenced in main()"
    assert "executeServer" in main_src, "REST server not started in main()"
    assert "add_endpoint" in main_src, "REST endpoints not registered in main()"

    assert "start_in_background" in worker_src, "MLLP server not started in run_mllp_worker()"
    assert "pipeline" in worker_src, "MLLP pipeline not started in run_mllp_worker()"
