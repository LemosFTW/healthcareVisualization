from __future__ import annotations

from typing import Any, Dict


class QueryMessageUsecase:
    """Retrieves a stored message envelope by ID."""

    def __init__(self, storage) -> None:
        self._storage = storage

    def execute(self, message_id: str) -> Dict[str, Any]:
        return self._storage.read({"id": message_id})
