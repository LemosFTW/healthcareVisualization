from __future__ import annotations

from typing import Optional

from healthcare_sdk import HealthCareStorage, HealthCareUsecase


class ListLogsUsecase(HealthCareUsecase):
    """Lists pipeline audit entries from message_log with pagination and filter."""

    def __init__(self, storage: HealthCareStorage) -> None:
        self._storage = storage

    def execute(
        self,
        page: int = 1,
        page_size: int = 10,
        status: Optional[str] = None,
    ) -> list[dict]:
        return self._storage.list_logs(
            page=page,
            page_size=page_size,
            status=status,
        )
