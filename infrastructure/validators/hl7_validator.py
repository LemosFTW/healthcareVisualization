from __future__ import annotations

from typing import List, Tuple

from healthcare_sdk import ValidationResult, ValidatorTemplate
from healthcare_sdk.contracts import ErrorDetail

# (field_name_in_decoded_dict, human-readable label)
_MSH_REQUIRED: List[Tuple[str, str]] = [
    ("message_type", "MSH.9 - Message Type"),
    ("message_control_id", "MSH.10 - Message Control ID"),
    ("datetime", "MSH.7 - Date/Time of Message"),
]

_PID_REQUIRED: List[Tuple[str, str]] = [
    ("patient_name", "PID.5 - Patient Name"),
]


class Hl7Validator(ValidatorTemplate):
    """Validates decoded payloads for minimum required fields.

    For HL7 v2 payloads (MSH present): validates required MSH/PID fields.
    For non-HL7 payloads (FHIR resourceType present): passes without HL7 checks.
    Returns ValidationResult with one ErrorDetail per missing or empty field.
    """

    def validate(self, decoded_payload: dict) -> ValidationResult:
        if not isinstance(decoded_payload, dict):
            return ValidationResult(
                is_valid=False,
                errors=[ErrorDetail(
                    code="invalid_payload_type",
                    message="Decoded payload must be a dictionary",
                    stage="validate",
                    context={"actual_type": type(decoded_payload).__name__},
                )],
            )

        errors: List[ErrorDetail] = []

        if "MSH" not in decoded_payload:
            # FHIR resources (and other non-HL7 formats) don't have MSH — pass through.
            # Only HL7 payloads that lack MSH entirely are considered invalid here.
            if "resourceType" in decoded_payload:
                return ValidationResult(is_valid=True, errors=[])
            errors.append(ErrorDetail(
                code="missing_segment",
                message="MSH segment is required but absent from decoded payload",
                stage="validate",
                context={"segment": "MSH"},
            ))
            return ValidationResult(is_valid=False, errors=errors)

        msh = decoded_payload["MSH"]
        for field_name, display_name in _MSH_REQUIRED:
            value = msh.get(field_name, "")
            if not (isinstance(value, str) and value.strip()):
                errors.append(ErrorDetail(
                    code="missing_required_field",
                    message=f"Required field {display_name} is missing or empty",
                    stage="validate",
                    context={"segment": "MSH", "field": field_name},
                ))

        # PID validation — only when PID segment is present
        if "PID" in decoded_payload:
            pid = decoded_payload["PID"]

            # At least one patient identifier (PID.2 or PID.3) must be present
            patient_id = pid.get("patient_id", "") or ""
            patient_id_list = pid.get("patient_identifier_list", "") or ""
            if not patient_id.strip() and not patient_id_list.strip():
                errors.append(ErrorDetail(
                    code="missing_patient_identifier",
                    message=(
                        "At least one patient identifier is required: "
                        "PID.2 (patient_id) or PID.3 (patient_identifier_list)"
                    ),
                    stage="validate",
                    context={"segment": "PID", "fields": ["patient_id", "patient_identifier_list"]},
                ))

            for field_name, display_name in _PID_REQUIRED:
                value = pid.get(field_name, "") or ""
                if not value.strip():
                    errors.append(ErrorDetail(
                        code="missing_required_field",
                        message=f"Required field {display_name} is missing or empty",
                        stage="validate",
                        context={"segment": "PID", "field": field_name},
                    ))

        return ValidationResult(is_valid=len(errors) == 0, errors=errors)
