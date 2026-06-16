from __future__ import annotations

from typing import Dict

from healthcare_sdk import Decoder, RawMessage
from healthcare_sdk.errors import DecodeError


class HealthcareDecoderRouter(Decoder):
    """Routes decode() calls to the appropriate concrete decoder by protocol.

    New decoders can be added via the constructor dict or register() without
    modifying the routing logic (open/closed principle, Story 1.6 AC3).

    Protocol matching is case-insensitive.
    """

    def __init__(self, decoders: Dict[str, Decoder]) -> None:
        self._decoders: Dict[str, Decoder] = {
            protocol.lower(): decoder for protocol, decoder in decoders.items()
        }

    def register(self, protocol: str, decoder: Decoder) -> None:
        """Register an additional decoder without touching existing dispatch logic."""
        self._decoders[protocol.lower()] = decoder

    def decode(self, raw_message: RawMessage) -> dict:
        protocol_key = (raw_message.protocol or "").lower()
        decoder = self._decoders.get(protocol_key)
        if decoder is None:
            supported = sorted(self._decoders.keys())
            raise DecodeError(
                f"No decoder registered for protocol {raw_message.protocol!r}. "
                f"Supported protocols: {supported}",
                context={"protocol": raw_message.protocol, "supported": supported},
            )
        return decoder.decode(raw_message)
