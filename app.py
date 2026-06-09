import os
import uuid

from fastapi import Request
from sqlalchemy import create_engine

from healthcare_sdk import (
    Adapter,
    AiHelper,
    Decoder,
    HealthCareStorage,
    HealthCareUsecase,
    Normalizer,
    PostgreSqlStorage,
    RawMessage,
    Validator,
    register_components,
    RestController,
)

from adapters import MllpConnector
from tools import (
    GeminiAiHelperStrategy,
    H7FhirDecoder,
    HealthcareNormalizer,
    Hl7Validator,
    Hl7V2Decoder,
)
from usecases import (
    CommitHealthCareMsgUsecase,
    ProcessHealthCareMsgUsecase,
    VisualizeHealthCareMsgUsecase,
)


def _make_handler(usecase: HealthCareUsecase):
    async def handler(request: Request):
        body = await request.json()
        raw_msg = RawMessage(
            id=body.get("id", str(uuid.uuid4())),
            protocol=body.get("protocol", "HL7v2"),
            raw_payload=body.get("raw_payload", ""),
            metadata=body.get("metadata", {}),
            message_type=body.get("message_type"),
        )
        envelope = usecase.execute(raw_msg)
        return {
            "id": envelope.id,
            "status": envelope.status,
            "protocol": envelope.protocol,
            "message_type": envelope.message_type,
            "metadata": envelope.metadata,
        }
    return handler


def main():
    postgres_user = os.getenv("POSTGRES_USER")
    postgres_password = os.getenv("POSTGRES_PASSWORD")
    postgres_host = os.getenv("POSTGRES_HOST")
    postgres_port = os.getenv("POSTGRES_PORT")
    postgres_db = os.getenv("POSTGRES_DB")
    postgres_dsn = (
        f"postgresql://{postgres_user}:{postgres_password}"
        f"@{postgres_host}:{postgres_port}/{postgres_db}"
    )

    engine = create_engine(postgres_dsn)

    process_usecase = ProcessHealthCareMsgUsecase()
    visualize_usecase = VisualizeHealthCareMsgUsecase()
    commit_usecase = CommitHealthCareMsgUsecase()

    adapters: list[Adapter] = [MllpConnector()]
    usecases: list[HealthCareUsecase] = [
        process_usecase,
        visualize_usecase,
        commit_usecase,
    ]
    validators: list[Validator] = [Hl7Validator()]
    decoders: list[Decoder] = [H7FhirDecoder(), Hl7V2Decoder()]
    ai_helpers: list[AiHelper] = [GeminiAiHelperStrategy()]
    normalizers: list[Normalizer] = [HealthcareNormalizer()]
    storages: list[HealthCareStorage] = [PostgreSqlStorage(engine)]

    register_components(
        adapters=adapters,
        usecases=usecases,
        validators=validators,
        decoders=decoders,
        aihelpers=ai_helpers,
        normalizers=normalizers,
        storages=storages,
    )

    rest_controller = RestController()
    rest_controller.add_endpoint("/process", "POST", _make_handler(process_usecase))
    rest_controller.add_endpoint("/visualize", "POST", _make_handler(visualize_usecase))
    rest_controller.add_endpoint("/commit", "POST", _make_handler(commit_usecase))
    rest_controller.executeServer(port=int(os.getenv("PORT", "8000")))


if __name__ == "__main__":
    main()
