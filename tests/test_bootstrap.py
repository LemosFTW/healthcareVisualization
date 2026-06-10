"""Tests for Story 1.1: Project Setup & Bootstrap."""
import os
import sys
import types
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch

from healthcare_sdk import (
    ComponentRegistrationError,
    RestController,
    register_components,
)
from healthcare_sdk.usecases import DefaultHealthCareUsecase

from infrastructure import (
    GeminiAiHelperStrategy,
    FhirDecoder,
    HealthcareNormalizer,
    Hl7Validator,
    Hl7V2Decoder,
)
from transport import MllpConnector


def _genai_mock_ctx():
    """Context manager that patches google.generativeai with a no-op mock."""
    genai_mock = MagicMock()
    genai_mock.GenerativeModel.return_value = MagicMock()
    google_pkg = types.ModuleType("google")
    google_pkg.generativeai = genai_mock
    return patch.dict(
        sys.modules,
        {"google": google_pkg, "google.generativeai": genai_mock},
    )


class _InvalidComponent:
    """Does not implement any SDK protocol — used to trigger ComponentRegistrationError."""
    pass


def test_health_endpoint_returns_200():
    """GET /health must return HTTP 200 with status ok."""
    controller = RestController()
    client = TestClient(controller.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_register_components_succeeds_with_valid_components():
    """register_components must not raise when all components satisfy SDK contracts."""
    with _genai_mock_ctx(), patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
        components = register_components(
            adapters=[MllpConnector()],
            validators=[Hl7Validator()],
            decoders=[Hl7V2Decoder(), FhirDecoder()],
            aihelpers=[GeminiAiHelperStrategy()],
            normalizers=[HealthcareNormalizer()],
        )
    assert components is not None


def test_register_components_raises_for_invalid_adapter():
    """register_components must raise ComponentRegistrationError for invalid adapter."""
    with pytest.raises(ComponentRegistrationError):
        register_components(adapters=[_InvalidComponent()])


def test_register_components_raises_for_invalid_decoder():
    """register_components must raise ComponentRegistrationError for invalid decoder."""
    with pytest.raises(ComponentRegistrationError):
        register_components(decoders=[_InvalidComponent()])


def test_register_components_raises_for_invalid_validator():
    """register_components must raise ComponentRegistrationError for invalid validator."""
    with pytest.raises(ComponentRegistrationError):
        register_components(validators=[_InvalidComponent()])


def test_layer_structure_exists():
    """domain/, usecases/, infrastructure/, transport/ directories must all exist."""
    base = os.path.dirname(os.path.dirname(__file__))
    for layer in ("domain", "usecases", "infrastructure", "transport"):
        layer_path = os.path.join(base, layer)
        assert os.path.isdir(layer_path), f"Missing layer directory: {layer}/"
        init = os.path.join(layer_path, "__init__.py")
        assert os.path.isfile(init), f"Missing {layer}/__init__.py"


def test_domain_layer_has_no_infrastructure_imports():
    """domain/__init__.py must not import from infrastructure or transport."""
    base = os.path.dirname(os.path.dirname(__file__))
    domain_init = os.path.join(base, "domain", "__init__.py")
    with open(domain_init) as f:
        source = f.read()
    forbidden = ("from infrastructure", "import infrastructure", "from transport", "import transport")
    for forbidden_import in forbidden:
        assert forbidden_import not in source, (
            f"domain layer contains forbidden import: {forbidden_import}"
        )
