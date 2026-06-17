"""Story 1.2 — GeminiAiHelper."""

import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest


def _make_genai_mock(response_text: str = "mocked response"):
    genai_mock = MagicMock()
    model_instance = MagicMock()
    model_instance.generate_content.return_value = MagicMock(text=response_text)
    genai_mock.GenerativeModel.return_value = model_instance
    return genai_mock, model_instance


def _patch_genai(genai_mock):
    google_pkg = types.ModuleType("google")
    google_pkg.generativeai = genai_mock
    return patch.dict(
        sys.modules, {"google": google_pkg, "google.generativeai": genai_mock}
    )


@pytest.mark.p0
def test_generate_response_returns_string():
    """
    Given a GeminiAiHelper instance with a mocked HTTP client
    When generateResponse() is called with a prompt
    Then the text returned by the Gemini REST API must be returned as a string
    """
    from tools.gemini_ai_helper_strategy import GeminiAiHelper

    fake_resp = MagicMock()
    fake_resp.raise_for_status = MagicMock()
    fake_resp.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": "Hello from Gemini"}]}}]
    }
    with patch(
        "tools.gemini_ai_helper_strategy.httpx.post", return_value=fake_resp
    ) as mock_post:
        helper = GeminiAiHelper(api_key="fake-key")
        result = helper.generateResponse("Say hello")
    assert result == "Hello from Gemini"
    mock_post.assert_called_once()


@pytest.mark.p0
def test_generate_response_raises_runtime_error_on_api_failure():
    """
    Given a GeminiAiHelper where the SDK raises an internal exception
    When generateResponse() is called
    Then RuntimeError must be raised without leaking SDK internals
    """
    genai_mock, model_instance = _make_genai_mock()
    model_instance.generate_content.side_effect = Exception("internal sdk error detail")
    with _patch_genai(genai_mock):
        from tools.gemini_ai_helper_strategy import GeminiAiHelper

        helper = GeminiAiHelper(api_key="fake-key")
        with pytest.raises(RuntimeError, match="Gemini API request failed"):
            helper.generateResponse("fail this")


@pytest.mark.p0
def test_init_raises_if_api_key_missing():
    """
    Given no GEMINI_API_KEY in environment and no key passed to constructor
    When GeminiAiHelper() is instantiated
    Then ValueError must be raised
    """
    genai_mock, _ = _make_genai_mock()
    with _patch_genai(genai_mock):
        from tools.gemini_ai_helper_strategy import GeminiAiHelper

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GEMINI_API_KEY", None)
            with pytest.raises(ValueError, match="GEMINI_API_KEY"):
                GeminiAiHelper()


@pytest.mark.p0
def test_api_key_read_from_env():
    """
    Given GEMINI_API_KEY set in environment
    When GeminiAiHelper() is instantiated without explicit key
    Then the helper must embed the env var value in its API URL
    """
    from tools.gemini_ai_helper_strategy import GeminiAiHelper

    with patch.dict(os.environ, {"GEMINI_API_KEY": "env-key-value"}):
        helper = GeminiAiHelper()
    assert "env-key-value" in helper._url


@pytest.mark.p0
def test_google_generativeai_not_imported_outside_helper():
    """
    Given all source files in domain, infrastructure, transport and usecases layers
    When scanning for google.generativeai imports
    Then the import must only appear in gemini_ai_helper_strategy.py
    """
    import os as _os

    base = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(__file__))))
    layers = ("domain", "infrastructure", "transport", "usecases", "tools")
    violations = []
    for layer in layers:
        layer_path = _os.path.join(base, layer)
        if not _os.path.isdir(layer_path):
            continue
        for root, _dirs, files in _os.walk(layer_path):
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                if fname == "gemini_ai_helper_strategy.py":
                    continue
                fpath = _os.path.join(root, fname)
                with open(fpath) as f:
                    source = f.read()
                if "google.generativeai" in source or "google-generativeai" in source:
                    violations.append(fpath)
    assert not violations, (
        f"google-generativeai imported outside GeminiAiHelper: {violations}"
    )
