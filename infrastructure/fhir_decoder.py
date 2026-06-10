from __future__ import annotations
import json
from typing import Any, Dict, List

from healthcare_sdk import Decoder, RawMessage
from healthcare_sdk.errors import DecodeError


class FhirDecoder(Decoder):
    """Decodes FHIR JSON payloads into structured dicts.

    Supports standalone FHIR resources (Patient, Observation, etc.) and Bundle.
    Raises DecodeError for invalid JSON or missing resourceType.
    """

    def decode(self, raw_message: RawMessage) -> dict:
        payload = raw_message.raw_payload
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8", errors="replace")

        payload = payload.strip()
        if not payload:
            raise DecodeError(
                "FHIR payload is empty",
                context={"raw_id": raw_message.id},
            )

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise DecodeError(
                f"FHIR payload is not valid JSON: {exc.msg} at position {exc.pos}",
                context={"raw_id": raw_message.id, "position": exc.pos},
            )

        if not isinstance(data, dict):
            raise DecodeError(
                f"FHIR payload must be a JSON object, got {type(data).__name__}",
                context={"raw_id": raw_message.id},
            )

        resource_type = data.get("resourceType")
        if not resource_type:
            raise DecodeError(
                "FHIR resource is missing required field 'resourceType'",
                context={"raw_id": raw_message.id, "keys": list(data.keys())},
            )

        result: Dict[str, Any] = {
            "resourceType": resource_type,
            "id": data.get("id", ""),
            "meta": data.get("meta", {}),
        }

        if resource_type == "Bundle":
            result["type"] = data.get("type", "")
            result["total"] = data.get("total", 0)
            result["resources"] = self._extract_bundle_resources(data)
        else:
            # Standalone resource — include all payload fields except those already extracted
            for key, value in data.items():
                if key not in ("resourceType", "id", "meta"):
                    result[key] = value

        return result

    def _extract_bundle_resources(self, bundle: dict) -> List[Dict[str, Any]]:
        resources: List[Dict[str, Any]] = []
        for entry in bundle.get("entry", []):
            resource = entry.get("resource")
            if isinstance(resource, dict):
                resources.append(resource)
        return resources
