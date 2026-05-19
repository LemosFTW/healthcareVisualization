from __future__ import annotations
from typing import Optional
from healthcare_sdk import Adapter, RawMessage

#TODO: Implement actual MLLP server logic here.
class MllpConnector(Adapter):
    def __init__(self, message: Optional[RawMessage] = None) -> None:
        self._message = message

    def executeServer(self, port: int = 8000):
        return {"status": "mllp_ready", "port": port}

    def receive(self) -> RawMessage:
        if self._message is None:
            raise ValueError("No RawMessage configured for MllpConnector")
        return self._message
