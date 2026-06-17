from healthcare_sdk import HealthCareUsecase


class ListMessagesUsecase(HealthCareUsecase):


    def __init__(self, storage) -> None:
        self._storage = storage

    def execute(self) -> list[dict]:
        return self._storage.list()
