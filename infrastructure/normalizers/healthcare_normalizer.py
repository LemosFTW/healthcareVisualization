from __future__ import annotations

import logging
from typing import Any, Dict, List

from healthcare_sdk import AiHelper, NormalizerTemplate
from healthcare_sdk.errors import NormalizationError

logger = logging.getLogger(__name__)


class HealthcareMessageNormalizer(NormalizerTemplate):
    """Converts decoded HL7 v2.3 and FHIR payloads to a standard internal format.

    Clinical observations are optionally analysed for anomalies by the
    AI helper set in self.aiHelper (NormalizerTemplate contract).
    """

    def __init__(self, ai_helper: AiHelper | None = None) -> None:
        super().__init__()
        self.aiHelper = ai_helper

    def normalizeData(self, decoded_payload: dict) -> dict:  # noqa: N802
        if not isinstance(decoded_payload, dict):
            raise NormalizationError(
                "decoded_payload must be a dictionary",
                context={"actual_type": type(decoded_payload).__name__},
            )

        # --- FHIR branch ---
        if decoded_payload.get("resourceType"):
            resource_type = decoded_payload.get("resourceType", "")
            resources = (
                decoded_payload.get("resources", [])
                if resource_type == "Bundle"
                else [decoded_payload]
            )

            patient_id = ""
            patient_name = ""
            date_of_birth = ""
            sex = ""
            clinical_observations: List[Dict[str, Any]] = []

            for res in resources:
                if not isinstance(res, dict):
                    continue
                rtype = res.get("resourceType", "")
                if rtype == "Patient":
                    name_list = res.get("name") or []
                    if name_list:
                        first = name_list[0]
                        given = " ".join(first.get("given") or [])
                        family = first.get("family", "")
                        patient_name = f"{given} {family}".strip()
                    patient_id = res.get("id", "")
                    date_of_birth = res.get("birthDate", "")
                    sex = res.get("gender", "")
                elif rtype == "Observation":
                    vq = res.get("valueQuantity") or {}
                    code_text = (res.get("code") or {}).get("text", "")
                    clinical_observations.append({
                        "identifier": f"{res.get('id', '')} - {code_text}".strip(" -"),
                        "value": str(vq.get("value", "")),
                        "units": vq.get("unit", ""),
                        "reference_range": "",
                        "abnormal_flags": "",
                        "status": res.get("status", ""),
                    })

            normalized: Dict[str, Any] = {
                "patient": {
                    "id": patient_id,
                    "name": patient_name,
                    "date_of_birth": date_of_birth,
                    "sex": sex,
                },
                "identifiers": {
                    "message_control_id": decoded_payload.get("id", ""),
                    "sending_application": "FHIR",
                    "sending_facility": (decoded_payload.get("meta") or {}).get(
                        "source", ""
                    ),
                },
                "message_type": resource_type,
                "datetime": "",
                "clinical_observations": clinical_observations,
                "warnings": [],
            }

            if self.aiHelper and clinical_observations:
                normalized["warnings"] = self._detect_anomalies(clinical_observations)

            return normalized

        # --- HL7 v2 branch ---
        msh = decoded_payload.get("MSH", {})
        pid = decoded_payload.get("PID", {})
        obx_raw = decoded_payload.get("OBX", [])
        obx_list = obx_raw if isinstance(obx_raw, list) else [obx_raw]

        patient_id = (
            pid.get("patient_identifier_list", "") or pid.get("patient_id", "")
        ).strip()

        clinical_observations = [
            {
                "identifier": obx.get("observation_identifier", ""),
                "value": obx.get("observation_value", ""),
                "units": obx.get("units", ""),
                "reference_range": obx.get("reference_range", ""),
                "abnormal_flags": obx.get("abnormal_flags", ""),
                "status": obx.get("observation_result_status", ""),
            }
            for obx in obx_list
            if isinstance(obx, dict)
        ]

        normalized = {
            "patient": {
                "id": patient_id,
                "name": pid.get("patient_name", ""),
                "date_of_birth": pid.get("date_of_birth", ""),
                "sex": pid.get("sex", ""),
            },
            "identifiers": {
                "message_control_id": msh.get("message_control_id", ""),
                "sending_application": msh.get("sending_application", ""),
                "sending_facility": msh.get("sending_facility", ""),
            },
            "message_type": msh.get("message_type", ""),
            "datetime": msh.get("datetime", ""),
            "clinical_observations": clinical_observations,
            "warnings": [],
        }

        if self.aiHelper and clinical_observations:
            normalized["warnings"] = self._detect_anomalies(clinical_observations)

        return normalized

    def _detect_anomalies(self, observations: List[Dict[str, Any]]) -> List[str]:
        logger.info("Detecting anomalies in %d observations via AI helper...", len(observations))  # noqa: E501
        prompt = self._build_anomaly_prompt(observations)
        try:
            response = self.aiHelper.generateResponse(prompt)
            logger.debug("AI helper response: %s", response)
            return self._parse_anomaly_response(response)
        except Exception as exc:
            logger.error("AI helper failed to analyze observations: %s", exc)
            return []

    def _build_anomaly_prompt(self, observations: List[Dict[str, Any]]) -> str:
        lines = [
            f"- {o['identifier']}: {o['value']} {o['units']} "
            f"(ref: {o['reference_range']}, flags: {o['abnormal_flags']})"
            for o in observations
            if o.get("value")
        ]
        obs_text = "\n".join(lines) if lines else "(no values)"
        return (
            "Analyze these clinical observations for clinically suspicious "
            "or dangerous values that may indicate patient risk "
            "(e.g. heart rate = 0, extreme out-of-range values):\n"
            f"{obs_text}\n\n"
            "For EACH suspicious finding respond with exactly ONE line:\n"
            "ANOMALY: <identifier> - <reason>\n"
            "If nothing is suspicious respond with exactly: NONE"
        )

    def _parse_anomaly_response(self, response: str) -> List[str]:
        if not response or "NONE" in response.upper():
            return []
        warnings: List[str] = []
        for line in response.strip().splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("ANOMALY:"):
                text = stripped[len("ANOMALY:"):].strip()
                if text:
                    warnings.append(text)
        print(f"Parsed anomalies: {warnings}")
        return warnings
