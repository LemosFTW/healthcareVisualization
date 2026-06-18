from __future__ import annotations

from typing import Optional

from healthcare_sdk import HealthCareStorage, HealthCareUsecase


class ListMessagesUsecase(HealthCareUsecase):
    """Lists stored messages with pagination and optional review_status filter."""

    def __init__(self, storage: HealthCareStorage) -> None:
        self._storage = storage

    def execute(
        self,
        page: int = 1,
        page_size: int = 10,
        review_status: Optional[str] = None,
    ) -> list[dict]:
        return self._storage.list(
            page=page,
            page_size=page_size,
            review_status=review_status,
        )
