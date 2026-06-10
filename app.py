import os

from sqlalchemy import create_engine

from healthcare_sdk import (
    Adapter,
    AiHelper,
    ComponentRegistrationError,
    Decoder,
    HealthCareStorage,
    HealthCareUsecase,
    Normalizer,
    PostgreSqlStorage,
    Validator,
    register_components,
    RestController,
)
from healthcare_sdk.usecases import DefaultHealthCareUsecase

from infrastructure import (
    GeminiAiHelper,
    FhirDecoder,
    HealthcareNormalizer,
    Hl7Validator,
    Hl7V2Decoder,
)
from transport import MllpConnector


def build_engine() -> object:
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    host = os.getenv("POSTGRES_HOST")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB")
    if all([user, password, host, db]):
        dsn = f"postgresql://{user}:{password}@{host}:{port}/{db}"
    else:
        dsn = os.getenv("DATABASE_URL", "sqlite:///healthcare.db")
    return create_engine(dsn)


def bootstrap():
    """Compose all concrete components and validate contracts via register_components."""
    engine = build_engine()
    storage = PostgreSqlStorage(engine)
    decoder = Hl7V2Decoder()
    validator = Hl7Validator()
    normalizer = HealthcareNormalizer()
    ai_helper = GeminiAiHelper()
    fhir_decoder = FhirDecoder()
    mllp_connector = MllpConnector()

    components = register_components(
        adapters=[mllp_connector],
        usecases=[],
        validators=[validator],
        decoders=[decoder, fhir_decoder],
        aihelpers=[ai_helper],
        normalizers=[normalizer],
        storages=[storage],
    )

    usecase = DefaultHealthCareUsecase(
        decoder=decoder,
        validator=validator,
        normalizer=normalizer,
        storage=storage,
    )

    return components, usecase, mllp_connector


def main():
    _components, _usecase, _mllp = bootstrap()

    rest_controller = RestController()
    rest_port = int(os.getenv("PORT", "8000"))
    rest_controller.executeServer(port=rest_port)


if __name__ == "__main__":
    main()
