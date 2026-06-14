"""Story 1.1 — Project Setup & Bootstrap."""
import os
import sys
import types
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from healthcare_sdk import ComponentRegistrationError, RestController, register_components
from healthcare_sdk.usecases import DefaultHealthCareUsecase
from infrastructure import GeminiAiHelper, FhirDecoder, HealthcareNormalizer, Hl7Validator, Hl7V2Decoder
from transport import MllpConnector

BASE = Path(__file__).parent.parent.parent


def _genai_mock_ctx():
    genai_mock = MagicMock()
    genai_mock.GenerativeModel.return_value = MagicMock()
    google_pkg = types.ModuleType("google")
    google_pkg.generativeai = genai_mock
    return patch.dict(sys.modules, {"google": google_pkg, "google.generativeai": genai_mock})


class _InvalidComponent:
    pass


@pytest.mark.p0
def test_health_endpoint_returns_200():
    """
    Given a running RestController
    When GET /health is called
    Then HTTP 200 with body {"status": "ok"} must be returned
    """
    controller = RestController()
    client = TestClient(controller.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.p0
def test_register_components_succeeds_with_valid_components():
    """
    Given valid SDK-compliant component instances
    When register_components() is called
    Then no ComponentRegistrationError must be raised
    """
    with _genai_mock_ctx(), patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
        from sqlalchemy import create_engine
        from healthcare_sdk import PostgreSqlStorage
        engine = create_engine("sqlite:///:memory:")
        storage = PostgreSqlStorage(engine)
        components = register_components(
            adapters=[MllpConnector()],
            usecases=[],
            validators=[Hl7Validator()],
            decoders=[Hl7V2Decoder(), FhirDecoder()],
            aihelpers=[GeminiAiHelper()],
            normalizers=[HealthcareNormalizer()],
            storages=[storage],
        )
    assert components is not None


@pytest.mark.p0
def test_register_components_raises_for_invalid_adapter():
    """
    Given a component that does not implement the Adapter protocol
    When register_components() is called with it as an adapter
    Then ComponentRegistrationError must be raised
    """
    with pytest.raises(ComponentRegistrationError):
        register_components(adapters=[_InvalidComponent()])


@pytest.mark.p0
def test_register_components_raises_for_invalid_decoder():
    """
    Given a component that does not implement the Decoder protocol
    When register_components() is called with it as a decoder
    Then ComponentRegistrationError must be raised
    """
    with pytest.raises(ComponentRegistrationError):
        register_components(decoders=[_InvalidComponent()])


@pytest.mark.p0
def test_register_components_raises_for_invalid_validator():
    """
    Given a component that does not implement the Validator protocol
    When register_components() is called with it as a validator
    Then ComponentRegistrationError must be raised
    """
    with pytest.raises(ComponentRegistrationError):
        register_components(validators=[_InvalidComponent()])


@pytest.mark.p0
def test_clean_architecture_layers_exist():
    """
    Given the project root
    When checking for clean architecture layer directories
    Then domain/, usecases/, infrastructure/ and transport/ must all exist with __init__.py
    """
    for layer in ("domain", "usecases", "infrastructure", "transport"):
        assert (BASE / layer).is_dir(), f"Missing layer: {layer}"
        assert (BASE / layer / "__init__.py").is_file(), f"Missing __init__.py in {layer}"


@pytest.mark.p0
def test_domain_layer_has_no_infrastructure_imports():
    """
    Given the domain/__init__.py source
    When scanning for forbidden imports
    Then no import from infrastructure or transport must be present
    """
    domain_init = BASE / "domain" / "__init__.py"
    source = domain_init.read_text()
    forbidden = ("from infrastructure", "import infrastructure", "from transport", "import transport")
    for forbidden_import in forbidden:
        assert forbidden_import not in source, f"domain layer contains forbidden import: {forbidden_import}"


@pytest.mark.p0
def test_bootstrap_function_runs_without_error():
    """
    Given environment variables for a SQLite in-memory database
    When bootstrap() is called
    Then all components must be returned without raising
    """
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    with _genai_mock_ctx(), patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
        from app import bootstrap
        components, usecase, mllp = bootstrap()
    assert components is not None
    assert usecase is not None
    assert mllp is not None
