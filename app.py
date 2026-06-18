import logging
import multiprocessing
import os

from dotenv import load_dotenv
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from healthcare_sdk import (
    Adapter,
    AiHelper,
    Decoder,
    HealthCareStorage,
    HealthCareUsecase,
    NormalizerTemplate,
    RestController,
    ValidatorTemplate,
    register_components,
)
from sqlalchemy import create_engine

from infrastructure import (
    FhirDecoder,
    HealthcareDecoderRouter,
    Hl7V2Decoder,
    Hl7Validator,
)
from infrastructure.normalizers.healthcare_normalizer import HealthcareMessageNormalizer
from repositories import PostgreSqlStorage
from tools import GeminiAiHelper
from transport import MllpConnector
from transport.messages_handler import (
    create_commit_message_handler,
    create_list_logs_handler,
    create_list_messages_handler,
    create_process_message_handler,
    create_query_message_handler,
)
from transport.mllp_pipeline import create_mllp_pipeline_loop
from usecases import (
    CommitMessageUsecase,
    ListLogsUsecase,
    ListMessagesUsecase,
    ProcessMessageUsecase,
    QueryMessageUsecase,
)

load_dotenv()

os.makedirs("logs", exist_ok=True)
_log_level = logging.getLevelName(os.getenv("LOG_LEVEL", "INFO"))
_formatter = logging.Formatter(
    fmt="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_file_handler = logging.FileHandler("logs/app.log", encoding="utf-8")
_file_handler.setFormatter(_formatter)
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_formatter)
logging.basicConfig(level=_log_level, handlers=[_file_handler, _console_handler])


def _register_exception_handlers(app) -> None:
    """Add RFC 9457 Problem Details handler for request validation errors."""

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "type": "about:blank",
                "title": "Unprocessable Content",
                "status": 422,
                "detail": str(exc),
            },
        )


def _build_ai_helper() -> AiHelper:
    provider = os.getenv("AI_PROVIDER", "gemini")
    apikey = os.getenv("GEMINI_API_KEY")
    if provider == "gemini":
        return GeminiAiHelper(api_key=apikey)
    raise ValueError(f"Unknown AI provider: {provider}")


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
    """Compose concrete components and validate contracts via register_components."""
    engine = build_engine()
    storage: HealthCareStorage = PostgreSqlStorage(engine)
    hl7_decoder: Decoder = Hl7V2Decoder()
    fhir_decoder: Decoder = FhirDecoder()
    router: Decoder = HealthcareDecoderRouter(
        {"hl7v2": hl7_decoder, "fhir": fhir_decoder}
    )
    validator: ValidatorTemplate = Hl7Validator()
    ai_helper: AiHelper = _build_ai_helper()
    normalizer: NormalizerTemplate = HealthcareMessageNormalizer(ai_helper=ai_helper)
    mllp_port = int(os.getenv("MLLP_PORT", "2575"))
    mllp_connector: Adapter = MllpConnector(port=mllp_port)

    process_usecase: HealthCareUsecase = ProcessMessageUsecase(
        decoder=router,
        validator=validator,
        normalizer=normalizer,
        storage=storage,
    )
    commit_usecase: HealthCareUsecase = CommitMessageUsecase(storage=storage)
    query_usecase: HealthCareUsecase = QueryMessageUsecase(storage=storage)
    list_usecase: HealthCareUsecase = ListMessagesUsecase(storage=storage)
    list_logs_usecase = ListLogsUsecase(storage=storage)
    components = register_components(
        adapters=[mllp_connector],
        usecases=[commit_usecase, query_usecase, process_usecase],
        validators=[validator],
        decoders=[router],
        aihelpers=[ai_helper],
        normalizers=[normalizer],
        storages=[storage],
    )
    return (
        components,
        process_usecase,
        commit_usecase,
        query_usecase,
        list_usecase,
        list_logs_usecase,
        mllp_connector,
    )


def run_mllp_worker() -> None:
    """Processo isolado: MLLP server + pipeline. Memória separada do REST."""
    _components, process_usecase, _commit, _query, _list, _list_logs, mllp = bootstrap()
    mllp.start_in_background()
    pipeline_loop = create_mllp_pipeline_loop(mllp, process_usecase)
    pipeline_loop()


def main():
    mllp_process = multiprocessing.Process(
        target=run_mllp_worker,
        daemon=True,
        name="mllp-worker",
    )
    mllp_process.start()

    (
        _components, process_usecase, commit_usecase,
        query_usecase, list_usecase, list_logs_usecase, _mllp,
    ) = bootstrap()

    rest_controller = RestController()
    _register_exception_handlers(rest_controller.app)
    rest_controller.add_endpoint(
        "/logs", "GET", create_list_logs_handler(list_logs_usecase)
    )
    rest_controller.add_endpoint(
        "/messages", "GET", create_list_messages_handler(list_usecase)
    )
    rest_controller.add_endpoint(
        "/messages", "POST", create_process_message_handler(process_usecase)
    )
    rest_controller.add_endpoint(
        "/messages/{id}", "GET", create_query_message_handler(query_usecase)
    )
    rest_controller.add_endpoint(
        "/messages/{id}/commit", "POST", create_commit_message_handler(commit_usecase)
    )

    rest_port = int(os.getenv("PORT", "8000"))
    rest_controller.executeServer(port=rest_port)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
