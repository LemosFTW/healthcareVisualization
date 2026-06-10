"""Tests for Story 1.7: PostgreSqlStorage with full MessageEnvelope persistence."""
import pytest
from sqlalchemy import create_engine, inspect

from healthcare_sdk.contracts import (
    ErrorDetail,
    MessageEnvelope,
    STATUS_STORED,
    STATUS_ERROR,
)

from infrastructure.postgres_storage import PostgreSqlStorage


def _make_engine():
    """SQLite in-memory engine — no real Postgres needed for unit tests."""
    return create_engine("sqlite:///:memory:")


def _make_stored_envelope(msg_id: str = "env-001") -> MessageEnvelope:
    env = MessageEnvelope(
        id=msg_id,
        protocol="hl7v2",
        message_type="ADT^A01",
        raw_payload="MSH|...",
        decoded_payload={"MSH": {"message_type": "ADT^A01"}},
        normalized_payload={"patient": {"id": "12345"}, "warnings": []},
        status=STATUS_STORED,
    )
    return env


def _make_error_envelope(msg_id: str = "env-err-001") -> MessageEnvelope:
    env = MessageEnvelope(
        id=msg_id,
        protocol="hl7v2",
        message_type="",
        raw_payload="BAD PAYLOAD",
        status=STATUS_ERROR,
    )
    env.errors.append(
        ErrorDetail(
            code="decode_error",
            message="MSH segment not found",
            stage="decode",
            context={"raw_id": msg_id},
        )
    )
    return env


# AC1: Tables created via Base.metadata.create_all on init
def test_tables_created_on_init():
    engine = _make_engine()
    PostgreSqlStorage(engine)
    insp = inspect(engine)
    table_names = insp.get_table_names()
    assert "healthcare_message_log" in table_names


# AC2: save() persists envelope and returns a string ID
def test_save_returns_string_id():
    storage = PostgreSqlStorage(_make_engine())
    returned_id = storage.save(_make_stored_envelope("env-001"))
    assert isinstance(returned_id, str)
    assert returned_id == "env-001"


def test_save_stored_envelope_persists_all_fields():
    storage = PostgreSqlStorage(_make_engine())
    env = _make_stored_envelope("env-002")
    storage.save(env)

    result = storage.read({"id": "env-002"})

    assert result["id"] == "env-002"
    assert result["protocol"] == "hl7v2"
    assert result["message_type"] == "ADT^A01"
    assert result["status"] == STATUS_STORED
    assert result["raw_payload"] == "MSH|..."
    assert result["decoded_payload"] == {"MSH": {"message_type": "ADT^A01"}}
    assert result["normalized_payload"]["patient"]["id"] == "12345"


# AC3: read({"id": id}) returns the persisted envelope
def test_read_existing_id_returns_data():
    storage = PostgreSqlStorage(_make_engine())
    storage.save(_make_stored_envelope("env-003"))

    result = storage.read({"id": "env-003"})
    assert result != {}
    assert result["id"] == "env-003"


def test_read_nonexistent_id_returns_empty_dict():
    storage = PostgreSqlStorage(_make_engine())
    result = storage.read({"id": "does-not-exist"})
    assert result == {}


def test_read_empty_query_returns_empty_dict():
    storage = PostgreSqlStorage(_make_engine())
    result = storage.read({})
    assert result == {}


# AC4: Error envelope with errors is persisted with all error fields intact
def test_save_error_envelope_preserves_errors():
    storage = PostgreSqlStorage(_make_engine())
    env = _make_error_envelope("env-err-001")
    storage.save(env)

    result = storage.read({"id": "env-err-001"})
    assert result["status"] == STATUS_ERROR
    assert isinstance(result["errors"], list)
    assert len(result["errors"]) == 1

    err = result["errors"][0]
    assert err["code"] == "decode_error"
    assert err["message"] == "MSH segment not found"
    assert err["stage"] == "decode"
    assert err["context"]["raw_id"] == "env-err-001"


def test_save_multiple_errors_all_persisted():
    storage = PostgreSqlStorage(_make_engine())
    env = _make_error_envelope("env-err-002")
    env.errors.append(
        ErrorDetail(
            code="validation_error",
            message="Missing message_type",
            stage="validate",
            context={"field": "message_type"},
        )
    )
    storage.save(env)

    result = storage.read({"id": "env-err-002"})
    assert len(result["errors"]) == 2
    codes = {e["code"] for e in result["errors"]}
    assert "decode_error" in codes
    assert "validation_error" in codes


def test_save_bytes_raw_payload_converted_to_string():
    storage = PostgreSqlStorage(_make_engine())
    env = _make_stored_envelope("env-bytes-001")
    env.raw_payload = b"MSH|binary payload"
    storage.save(env)

    result = storage.read({"id": "env-bytes-001"})
    assert isinstance(result["raw_payload"], str)
    assert "MSH" in result["raw_payload"]
