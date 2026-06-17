from __future__ import annotations

import os

import httpx
from healthcare_sdk import AiHelper

_GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent"


class GeminiAiHelper(AiHelper):
    """Implements AiHelper calling the Gemini REST API directly (no SDK dependency).

    API key is read from the GEMINI_API_KEY environment variable.
    """

    def __init__(self, api_key: str | None = None) -> None:
        resolved_key = api_key or os.getenv("GEMINI_API_KEY", "")
        if not resolved_key:
            raise ValueError(
                "GeminiAiHelper requires a Gemini API key. "
                "Set the GEMINI_API_KEY environment variable."
            )
        self._url = f"{_GEMINI_BASE}?key={resolved_key}"

    def generateResponse(self, prompt: str) -> str:  # noqa: N802
        try:
            resp = httpx.post(
                self._url,
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as exc:
            print(f"Gemini API request failed: {exc}")
            raise RuntimeError(f"Gemini API request failed: {exc}") from None
