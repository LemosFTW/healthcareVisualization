from healthcare_sdk import register_components, Adapter, HealthCareUsecase, Validator, Decoder, AiHelper, Normalizer, HealthCareStorage




def main():
    adapters : list[Adapter] = []
    usecases : list[HealthCareUsecase] = []
    validators : list[Validator] = []
    decoders : list[Decoder] = []
    ai_helpers : list[AiHelper] = []
    normalizers : list[Normalizer] = []
    storage : list[HealthCareStorage] = []
    instance = register_components(adapters=adapters, usecases=usecases, validators=validators, decoders=decoders, ai_helpers=ai_helpers, normalizers=normalizers, storage=storage)
    



if __name__ == "__main__":
    main()