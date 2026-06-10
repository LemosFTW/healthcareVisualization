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
    Validator,
    register_components,
    RestController,
)
from healthcare_sdk.usecases import DefaultHealthCareUsecase

from infrastructure import (
    GeminiAiHelper,
    FhirDecoder,
    HealthcareDecoderRouter,
    HealthcareNormalizer,
    Hl7Validator,
    Hl7V2Decoder,
    PostgreSqlStorage,
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
    hl7_decoder = Hl7V2Decoder()
    fhir_decoder = FhirDecoder()
    router = HealthcareDecoderRouter({"hl7v2": hl7_decoder, "fhir": fhir_decoder})

    validator = Hl7Validator()
    ai_helper = GeminiAiHelper()
    normalizer = HealthcareNormalizer()
    normalizer.aiHelper = ai_helper  # wire AI helper for anomaly detection
    mllp_connector = MllpConnector()

    components = register_components(
        adapters=[mllp_connector],
        usecases=[],
        validators=[validator],
        decoders=[router],
        aihelpers=[ai_helper],
        normalizers=[normalizer],
        storages=[storage],
    )

    usecase = DefaultHealthCareUsecase(
        decoder=router,
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
