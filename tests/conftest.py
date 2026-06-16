"""Shared test infrastructure — fake components and common fixtures."""
import pytest
from healthcare_sdk.contracts import (
    MessageEnvelope,
    RawMessage,
    ValidationResult,
)


class FakeDecoder:
    def decode(self, raw_message: RawMessage) -> dict:
        return {"source": raw_message.protocol, "data": raw_message.raw_payload}


class FakeValidator:
    def validate(self, decoded_payload: dict) -> ValidationResult:
        return ValidationResult(is_valid=True, errors=[])


class FakeNormalizer:
    def normalizeData(self, decoded_payload: dict) -> dict:
        return {**decoded_payload, "warnings": []}


class FakeStorage:
    def __init__(self):
        self._store: dict = {}

    def save(self, envelope: MessageEnvelope) -> str:
        self._store[envelope.id] = envelope
        return envelope.id

    def read(self, query: dict) -> dict:
        msg_id = query.get("id")
        if not msg_id or msg_id not in self._store:
            return {}
        env = self._store[msg_id]
        return {"id": env.id, "status": env.status, "protocol": env.protocol}

    def update(self, query: dict, data: dict) -> None:
        msg_id = query.get("id")
        if msg_id and msg_id in self._store:
            self._store[msg_id] = data

    def delete(self, query: dict) -> None:
        msg_id = query.get("id")
        if msg_id:
            self._store.pop(msg_id, None)

    def connection(self):
        return None


@pytest.fixture
def fake_decoder():
    return FakeDecoder()


@pytest.fixture
def fake_validator():
    return FakeValidator()


@pytest.fixture
def fake_normalizer():
    return FakeNormalizer()


@pytest.fixture
def fake_storage():
    return FakeStorage()


@pytest.fixture
def valid_hl7_payload() -> str:
    return (
        r"MSH|^~\&|SendApp|SendFac|RecApp|RecFac|20230601120000||ADT^A01|MSG001|P|2.3"
        + "\rPID|1||12345^^^MRN||Doe^John^A||19800101|M"
    )


@pytest.fixture
def valid_fhir_payload() -> str:
    import json
    return json.dumps({
        "resourceType": "Patient",
        "id": "patient-001",
        "name": [{"family": "Doe", "given": ["John"]}],
        "gender": "male",
        "birthDate": "1980-01-01",
    })
