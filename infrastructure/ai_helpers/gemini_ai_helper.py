from __future__ import annotations
from healthcare_sdk import AiHelper


class GeminiAiHelper(AiHelper):
    def generateResponse(self, prompt: str) -> str:
        return f"gemini-response: {prompt}"
