from __future__ import annotations
from healthcare_sdk import NormalizerTemplate

class HealthcareNormalizer(NormalizerTemplate):
    def normalizeData(self, decoded_payload):
        return {
            "normalized": True,
            "payload": decoded_payload,
        }
