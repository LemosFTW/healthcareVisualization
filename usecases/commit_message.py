from __future__ import annotations

from healthcare_sdk import HealthCareStorage
from healthcare_sdk.usecases import HealthCareUsecase


class CommitMessageUsecase(HealthCareUsecase):
    """Approves a pending message, marking it as reviewed in the database."""

    def __init__(self, storage: HealthCareStorage) -> None:
        self._storage = storage

    def execute(self, message_id: str) -> bool:
        return self._storage.update(
            {"id": message_id},
            {"review_status": "approved"},
        )
