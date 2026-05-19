from __future__ import annotations
from healthcare_sdk import ValidationResult, ValidatorTemplate

class Hl7Validator(ValidatorTemplate):
    def validate(self, decoded_payload):
        errors = []
        if decoded_payload is None:
            errors.append({"message": "Decoded payload is empty"})
        return ValidationResult(is_valid=not errors, errors=errors)
