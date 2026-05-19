import os

from healthcare_sdk import (
    Adapter,
    AiHelper,
    Decoder,
    HealthCareStorage,
    HealthCareUsecase,
    Normalizer,
    PostgreSqlStorage,
    Validator,
    register_components,
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

    adapters: list[Adapter] = [MllpConnector()]
    usecases: list[HealthCareUsecase] = [
        ProcessHealthCareMsgUsecase(),
        VisualizeHealthCareMsgUsecase(),
        CommitHealthCareMsgUsecase(),
    ]
    validators: list[Validator] = [Hl7Validator()]
    decoders: list[Decoder] = [H7FhirDecoder(), Hl7V2Decoder()]
    ai_helpers: list[AiHelper] = [GeminiAiHelperStrategy()]
    normalizers: list[Normalizer] = [HealthcareNormalizer()]
    storages: list[HealthCareStorage] = [PostgreSqlStorage(postgres_dsn)]
    instance = register_components(
        adapters=adapters,
        usecases=usecases,
        validators=validators,
        decoders=decoders,
        aihelpers=ai_helpers,
        normalizers=normalizers,
        storages=storages,
    )
    



if __name__ == "__main__":
    main()
