from __future__ import annotations

from typing import Any, Dict, List

from healthcare_sdk import NormalizerTemplate
from healthcare_sdk.errors import NormalizationError


class HealthcareMessageNormalizer(NormalizerTemplate):
    """Converts decoded HL7 v2.3 payloads to a standard internal format.

    Clinical observations are optionally analysed for anomalies by the
    AI helper set in self.aiHelper (NormalizerTemplate contract).
    """

    def __init__(self, ai_helper=None) -> None:
        super().__init__()
        self.aiHelper = ai_helper

    def normalizeData(self, decoded_payload: dict) -> dict:  # noqa: N802
        if not isinstance(decoded_payload, dict):
            raise NormalizationError(
                "decoded_payload must be a dictionary",
                context={"actual_type": type(decoded_payload).__name__},
            )

        msh = decoded_payload.get("MSH", {})
        pid = decoded_payload.get("PID", {})
        obx_raw = decoded_payload.get("OBX", [])
        obx_list = obx_raw if isinstance(obx_raw, list) else [obx_raw]

        patient_id = (
            pid.get("patient_identifier_list", "") or pid.get("patient_id", "")
        ).strip()

        # HL7 OBX observations
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

        # FHIR Observation resources (Bundle entry or standalone) — supplement HL7 OBX
        if not clinical_observations:
            fhir_resources = decoded_payload.get("resources", [])
            if isinstance(fhir_resources, list):
                for res in fhir_resources:
                    if (
                        isinstance(res, dict)
                        and res.get("resourceType") == "Observation"
                    ):
                        vq = res.get("valueQuantity") or {}
                        code_text = (res.get("code") or {}).get("text", "")
                        clinical_observations.append(
                            {
                                "identifier": f"{res.get('id', '')} - {code_text}",
                                "value": str(vq.get("value", "")),
                                "units": vq.get("unit", ""),
                                "reference_range": "",
                                "abnormal_flags": "",
                                "status": res.get("status", ""),
                            }
                        )

        normalized: Dict[str, Any] = {
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
        print(
            f"Detecting anomalies in {len(observations)} observations via AI helper..."
        )
        prompt = self._build_anomaly_prompt(observations)
        print(f"Anomaly detection prompt:\n{prompt}")
        try:
            print("Sending prompt to AI helper...")
            response = self.aiHelper.generateResponse(prompt)
            print(f"AI helper response:\n{response}")
            return self._parse_anomaly_response(response)
        except Exception:
            print("AI helper failed to analyze observations for anomalies.")
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
                text = stripped[len("ANOMALY:") :].strip()
                if text:
                    warnings.append(text)
        print(f"Parsed anomalies: {warnings}")
        return warnings
