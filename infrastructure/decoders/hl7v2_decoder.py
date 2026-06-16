from __future__ import annotations

from typing import Any, Dict, List

from healthcare_sdk import Decoder, RawMessage
from healthcare_sdk.errors import DecodeError

# Field name maps for common HL7 v2.3 segments.
# Indices are 0-based into fields[1:] (i.e., after stripping the segment name).
# HL7 field number = index + 1 for most segments; MSH is MSH.(index+2) because MSH.1 is
# the separator character itself and is never stored as a data field.
_MSH_FIELDS: Dict[int, str] = {
    0: "encoding_characters",    # MSH.2
    1: "sending_application",    # MSH.3
    2: "sending_facility",       # MSH.4
    3: "receiving_application",  # MSH.5
    4: "receiving_facility",     # MSH.6
    5: "datetime",               # MSH.7
    6: "security",               # MSH.8
    7: "message_type",           # MSH.9
    8: "message_control_id",     # MSH.10
    9: "processing_id",          # MSH.11
    10: "version_id",            # MSH.12
}

_PID_FIELDS: Dict[int, str] = {
    0: "set_id",                    # PID.1
    1: "patient_id",                # PID.2
    2: "patient_identifier_list",   # PID.3
    3: "alternate_patient_id",      # PID.4
    4: "patient_name",              # PID.5
    5: "mothers_maiden_name",       # PID.6
    6: "date_of_birth",             # PID.7
    7: "sex",                       # PID.8
    8: "patient_alias",             # PID.9
    9: "race",                      # PID.10
    10: "patient_address",          # PID.11
    12: "phone_home",               # PID.13
    13: "phone_business",           # PID.14
    17: "patient_account_number",   # PID.18
    18: "ssn",                      # PID.19
}

_OBR_FIELDS: Dict[int, str] = {
    0: "set_id",                # OBR.1
    1: "placer_order_number",   # OBR.2
    2: "filler_order_number",   # OBR.3
    3: "universal_service_id",  # OBR.4
    5: "requested_datetime",    # OBR.6
    6: "observation_datetime",  # OBR.7
    14: "specimen_source",      # OBR.15
    15: "ordering_provider",    # OBR.16
    24: "result_status",        # OBR.25
}

_OBX_FIELDS: Dict[int, str] = {
    0: "set_id",                        # OBX.1
    1: "value_type",                    # OBX.2
    2: "observation_identifier",        # OBX.3
    3: "observation_sub_id",            # OBX.4
    4: "observation_value",             # OBX.5
    5: "units",                         # OBX.6
    6: "reference_range",               # OBX.7
    7: "abnormal_flags",                # OBX.8
    10: "observation_result_status",    # OBX.11
    13: "date_last_obs_normal_values",  # OBX.14
}

_SEGMENT_MAPS: Dict[str, Dict[int, str]] = {
    "MSH": _MSH_FIELDS,
    "PID": _PID_FIELDS,
    "OBR": _OBR_FIELDS,
    "OBX": _OBX_FIELDS,
}

# Segments that may repeat in a single message
_REPEATING_SEGMENTS = {"OBR", "OBX", "NTE", "GT1", "IN1", "DG1", "AL1"}


def _map_fields(
    seg_name: str, fields: List[str], field_map: Dict[int, str]
) -> Dict[str, Any]:
    """Convert a list of raw field strings into a named dict using the given map."""
    result: Dict[str, Any] = {"_raw_fields": fields}
    for idx, name in field_map.items():
        value = fields[idx] if idx < len(fields) else ""
        result[name] = value
    return result


def _parse_segment(seg_name: str, fields: List[str]) -> Dict[str, Any]:
    """Parse one segment's field list into a structured dict.

    For MSH, fields[1] is encoding chars (MSH.2); for other segments
    fields[1] is the first data field.
    """
    field_map = _SEGMENT_MAPS.get(seg_name, {})
    if not field_map:
        # Unknown segment — return generic field_1..field_N structure
        result: Dict[str, Any] = {"_raw_fields": fields}
        for i, val in enumerate(fields[1:], start=1):
            result[f"field_{i}"] = val
        return result

    # For MSH, the standard field numbering counts the separator itself as MSH.1,
    # so fields[1] maps to MSH.2 (encoding_characters), fields[2] to MSH.3, etc.
    # We store fields[1:] and map using 1-based indices directly.
    return _map_fields(seg_name, fields[1:], field_map)


class Hl7V2Decoder(Decoder):
    """Decodes HL7 v2.3 messages from RawMessage into a structured segment dict.

    Raises DecodeError for malformed or empty payloads.
    """

    def decode(self, raw_message: RawMessage) -> dict:
        text = self._normalize_payload(raw_message.raw_payload)
        raw_segments = [s.strip() for s in text.split("\r") if s.strip()]

        if not raw_segments:
            raise DecodeError(
                "HL7 payload contains no segments",
                context={"raw_id": raw_message.id},
            )

        field_sep = self._validate_msh(raw_segments[0], raw_message.id)
        return self._parse_all_segments(raw_segments, field_sep)

    def _normalize_payload(self, payload: Any) -> str:
        if isinstance(payload, bytes):
            payload = payload.decode("latin-1", errors="replace")
        return payload.strip().replace("\r\n", "\r").replace("\n", "\r")

    def _validate_msh(self, first: str, raw_id: str) -> str:
        """Validate MSH is the first segment and extract the field separator."""
        if not first.startswith("MSH"):
            raise DecodeError(
                f"HL7 payload must begin with MSH segment, found: {first[:3]!r}",
                context={"raw_id": raw_id},
            )
        if len(first) < 8:
            raise DecodeError(
                "MSH segment too short to contain required encoding characters",
                context={"msh_snippet": first[:20]},
            )
        field_sep = first[3]  # position 3 is the field separator (usually '|')
        if field_sep.isalnum() or not field_sep.isprintable():
            raise DecodeError(
                f"Invalid HL7 field separator: {field_sep!r}",
                context={"msh_snippet": first[:20]},
            )
        return field_sep

    def _parse_all_segments(
        self, raw_segments: List[str], field_sep: str
    ) -> Dict[str, Any]:
        """Iterate all segments and build the structured result dict."""
        result: Dict[str, Any] = {}
        segment_order: List[str] = []

        for raw_seg in raw_segments:
            seg_name = raw_seg[:3].upper()
            if not seg_name.isalpha():
                continue  # skip garbage lines

            fields = raw_seg.split(field_sep)
            parsed = _parse_segment(seg_name, fields)

            if seg_name in _REPEATING_SEGMENTS:
                if seg_name not in result:
                    result[seg_name] = []
                result[seg_name].append(parsed)
            else:
                result[seg_name] = parsed

            if seg_name not in segment_order:
                segment_order.append(seg_name)

        result["_segment_order"] = segment_order
        return result
