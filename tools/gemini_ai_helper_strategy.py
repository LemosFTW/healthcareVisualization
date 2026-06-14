from __future__ import annotations
import os

from healthcare_sdk import AiHelper


class GeminiAiHelper(AiHelper):
    """Implements AiHelper using the Gemini API.

    All google-generativeai imports are local to this class — no other layer
    may import google.generativeai directly (NFR8).

    API key is read from the GEMINI_API_KEY environment variable.
    """

    def __init__(self, api_key: str | None = None) -> None:
        import google.generativeai as genai  # encapsulated SDK import

        resolved_key = api_key or os.getenv("GEMINI_API_KEY", "")
        if not resolved_key:
            raise ValueError(
                "GeminiAiHelper requires a Gemini API key. "
                "Set the GEMINI_API_KEY environment variable."
            )
        genai.configure(api_key=resolved_key)
        self._model = genai.GenerativeModel("gemini-1.5-flash")

    def generateResponse(self, prompt: str) -> str:
        """Call Gemini and return the generated text.

        Raises RuntimeError with a descriptive message on API failure
        without leaking internal SDK details.
        """
        try:
            response = self._model.generate_content(prompt)
            return response.text
        except Exception as exc:
            raise RuntimeError(
                f"Gemini API request failed: {exc}"
            ) from None
