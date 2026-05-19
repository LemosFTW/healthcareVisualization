from __future__ import annotations
from healthcare_sdk import Decoder, RawMessage

class H7FhirDecoder(Decoder):
    def decode(self, raw_message: RawMessage):
        return {
            "id": raw_message.id,
            "protocol": raw_message.protocol,
            "payload": raw_message.raw_payload,
            "format": "FHIR",
        }
