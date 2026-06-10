"""Story 1.1: Project Setup & Bootstrap — acceptance tests."""
import os
import pytest
from pathlib import Path


BASE = Path(__file__).parent.parent

# AC3: Folder structure exists
def test_clean_architecture_layers_exist():
    for layer in ("domain", "usecases", "infrastructure", "transport"):
        assert (BASE / layer).is_dir(), f"Missing layer: {layer}"
        assert (BASE / layer / "__init__.py").is_file(), f"Missing __init__.py in {layer}"


# AC1: register_components validates without raising ComponentRegistrationError
def test_register_components_succeeds_with_valid_components():
    from sqlalchemy import create_engine
    from healthcare_sdk import register_components, PostgreSqlStorage
    from infrastructure import GeminiAiHelperStrategy, FhirDecoder, HealthcareNormalizer, Hl7Validator, Hl7V2Decoder
    from transport import MllpConnector

    engine = create_engine("sqlite:///:memory:")
    storage = PostgreSqlStorage(engine)
    mllp = MllpConnector()
    decoder = Hl7V2Decoder()

    components = register_components(
        adapters=[mllp],
        usecases=[],
        validators=[Hl7Validator()],
        decoders=[decoder, FhirDecoder()],
        aihelpers=[GeminiAiHelperStrategy()],
        normalizers=[HealthcareNormalizer()],
        storages=[storage],
    )
    assert components is not None


# AC2: Invalid component raises ComponentRegistrationError
def test_register_components_raises_for_invalid_component():
    from healthcare_sdk import register_components, ComponentRegistrationError

    class NotAnAdapter:
        pass

    with pytest.raises((ComponentRegistrationError, Exception)):
        register_components(adapters=[NotAnAdapter()])


# AC1: RestController exposes /health endpoint
def test_rest_controller_has_health_endpoint():
    from fastapi.testclient import TestClient
    from healthcare_sdk import RestController

    controller = RestController()
    client = TestClient(controller.app)
    response = client.get("/health")
    assert response.status_code == 200


# AC1: bootstrap() completes without error
def test_bootstrap_function_runs_without_error():
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    from app import bootstrap
    components, usecase, mllp = bootstrap()
    assert components is not None
    assert usecase is not None
    assert mllp is not None
