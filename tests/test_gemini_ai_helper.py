"""Tests for Story 1.2: GeminiAiHelper."""
import os
import sys
import types
import pytest
from unittest.mock import MagicMock, patch


def _make_genai_mock(response_text: str = "mocked response"):
    """Build a minimal google.generativeai mock that satisfies GeminiAiHelper."""
    genai_mock = MagicMock()
    model_instance = MagicMock()
    model_instance.generate_content.return_value = MagicMock(text=response_text)
    genai_mock.GenerativeModel.return_value = model_instance
    return genai_mock, model_instance


def _patch_genai(genai_mock):
    """Insert the mock into sys.modules so local imports inside the class hit it."""
    google_pkg = types.ModuleType("google")
    google_pkg.generativeai = genai_mock
    return patch.dict(
        sys.modules,
        {
            "google": google_pkg,
            "google.generativeai": genai_mock,
        },
    )


def test_generate_response_returns_string():
    """generateResponse must return the text produced by Gemini."""
    genai_mock, model_instance = _make_genai_mock("Hello from Gemini")

    with _patch_genai(genai_mock):
        from infrastructure.gemini_ai_helper import GeminiAiHelper

        helper = GeminiAiHelper(api_key="fake-key")
        result = helper.generateResponse("Say hello")

    assert result == "Hello from Gemini"
    model_instance.generate_content.assert_called_once_with("Say hello")


def test_generate_response_raises_runtime_error_on_api_failure():
    """generateResponse must raise RuntimeError without leaking SDK internals."""
    genai_mock, model_instance = _make_genai_mock()
    model_instance.generate_content.side_effect = Exception("internal sdk error detail")

    with _patch_genai(genai_mock):
        from infrastructure.gemini_ai_helper import GeminiAiHelper

        helper = GeminiAiHelper(api_key="fake-key")
        with pytest.raises(RuntimeError, match="Gemini API request failed"):
            helper.generateResponse("fail this")


def test_init_raises_if_api_key_missing():
    """GeminiAiHelper must raise ValueError when no API key is available."""
    genai_mock, _ = _make_genai_mock()

    with _patch_genai(genai_mock):
        from infrastructure.gemini_ai_helper import GeminiAiHelper

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GEMINI_API_KEY", None)
            with pytest.raises(ValueError, match="GEMINI_API_KEY"):
                GeminiAiHelper()


def test_api_key_read_from_env():
    """GeminiAiHelper must configure Gemini using the GEMINI_API_KEY env var."""
    genai_mock, _ = _make_genai_mock()

    with _patch_genai(genai_mock):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "env-key-value"}):
            from infrastructure.gemini_ai_helper import GeminiAiHelper

            GeminiAiHelper()

    genai_mock.configure.assert_called_once_with(api_key="env-key-value")


def test_google_generativeai_not_imported_outside_helper():
    """No other infrastructure/transport/domain/usecases file may import google.generativeai."""
    base = os.path.join(os.path.dirname(os.path.dirname(__file__)))
    layers = ("domain", "infrastructure", "transport", "usecases")
    violations = []

    for layer in layers:
        layer_path = os.path.join(base, layer)
        if not os.path.isdir(layer_path):
            continue
        for root, _dirs, files in os.walk(layer_path):
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                if fname == "gemini_ai_helper.py":
                    continue  # this is the only allowed file
                fpath = os.path.join(root, fname)
                with open(fpath) as f:
                    source = f.read()
                if "google.generativeai" in source or "google-generativeai" in source:
                    violations.append(fpath)

    assert not violations, (
        f"google-generativeai imported outside GeminiAiHelper: {violations}"
    )
