from healthcare_sdk import HealthCareStorage, HealthCareUsecase

### pelo oq eu vi storage como parametro está de acordo com clean code/ hexagonal

class ListMessagesUsecase(HealthCareUsecase):


    def __init__(self, storage : HealthCareStorage) -> None:
        self._storage = storage

    def execute(self) -> list[dict]:
        return self._storage.list()
