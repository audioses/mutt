"""Unit tests for ai_translator.AITranslator.

These tests exercise the critical regressions fixed in the audit:
- `self._client` vs `self.client` (attribute name consistency)
- `response.choices[0].message.content` indexing
- Flexible custom OpenAI-compatible base_url handling
- Provider-specific client construction branches
"""
from __future__ import annotations

import pytest

from ai_translator import AITranslator


# ---------- Client initialization ----------------------------------------

def test_init_defaults_do_not_touch_network():
    """Constructor must be side-effect free until _initialize_client is called."""
    t = AITranslator("OpenAI GPT", "sk-abc", "gpt-4o-mini")
    assert t.api_provider == "OpenAI GPT"
    assert t.api_key == "sk-abc"
    assert t.model_name == "gpt-4o-mini"
    assert t._client is None
    assert t._client_initialized is False


def test_openai_client_constructed_with_api_key(fake_openai):
    t = AITranslator("OpenAI GPT", "sk-abc", "gpt-4o-mini")
    t._initialize_client()
    assert len(fake_openai) == 1
    assert fake_openai[0].api_key == "sk-abc"
    assert fake_openai[0].base_url is None  # vanilla OpenAI — no base_url override


def test_openrouter_client_uses_openrouter_base_url(fake_openai):
    t = AITranslator("OpenRouter", "sk-or", "anthropic/claude-3-haiku")
    t._initialize_client()
    assert fake_openai[0].base_url == "https://openrouter.ai/api/v1"
    assert fake_openai[0].api_key == "sk-or"


def test_custom_openai_compatible_requires_base_url():
    t = AITranslator(
        "Custom (OpenAI-Compatible)", "k", "llama-3",
        extra_settings={},  # no base_url
    )
    with pytest.raises(ValueError, match="base_url"):
        t._initialize_client()


def test_custom_openai_compatible_accepts_any_base_url(fake_openai):
    t = AITranslator(
        "Custom (OpenAI-Compatible)", "k", "llama-3",
        extra_settings={"base_url": "https://api.groq.com/openai/v1"},
    )
    t._initialize_client()
    assert fake_openai[0].base_url == "https://api.groq.com/openai/v1"
    assert fake_openai[0].api_key == "k"


def test_custom_openai_compatible_blank_api_key_still_works(fake_openai):
    """Some self-hosted endpoints reject empty keys — we substitute a placeholder."""
    t = AITranslator(
        "Custom (OpenAI-Compatible)", "", "llama-3",
        extra_settings={"base_url": "http://localhost:8080/v1"},
    )
    t._initialize_client()
    assert fake_openai[0].api_key == "not-needed"


def test_custom_openai_compatible_trims_whitespace(fake_openai):
    t = AITranslator(
        "Custom (OpenAI-Compatible)", "k", "m",
        extra_settings={"base_url": "  http://localhost:8080/v1  "},
    )
    t._initialize_client()
    assert fake_openai[0].base_url == "http://localhost:8080/v1"


def test_initialize_client_is_idempotent(fake_openai):
    t = AITranslator("OpenAI GPT", "sk-abc", "m")
    t._initialize_client()
    t._initialize_client()
    t._initialize_client()
    assert len(fake_openai) == 1  # Only constructed once


def test_argos_and_huggingface_skip_client_construction(fake_openai):
    for provider in ("Argos Translate", "HuggingFace"):
        t = AITranslator(provider, "", "m")
        t._initialize_client()
        assert t._client is None
    assert fake_openai == []


def test_unsupported_provider_raises():
    t = AITranslator("Telepathy-as-a-Service", "k", "m")
    with pytest.raises(ValueError, match="Unsupported API provider"):
        t._initialize_client()


# ---------- Attribute access regression ----------------------------------

def test_execute_prompt_uses_private_underscore_client(fake_openai):
    """Regression: previously line 438 used self.client (missing underscore)."""
    t = AITranslator("OpenAI GPT", "sk", "gpt-4o-mini")
    t._initialize_client()
    content, usage = t._execute_prompt_with_usage("sys", "user")
    assert content == "translated-text"
    assert usage == {"prompt_tokens": 10, "completion_tokens": 20}


def test_execute_prompt_indexes_choices_at_zero(fake_openai):
    """Regression: previously `response.choices.message.content` (missing [0])."""
    t = AITranslator("OpenRouter", "sk", "m")
    t._initialize_client()
    content, _ = t._execute_prompt_with_usage("s", "u")
    # If [0] were missing, we'd get AttributeError here — we got through.
    assert isinstance(content, str)


def test_execute_single_prompt_openai_path(fake_openai):
    t = AITranslator("Custom (OpenAI-Compatible)", "k", "m",
                     extra_settings={"base_url": "http://x/v1"})
    out, _ = t._execute_single_prompt("hello")
    assert out == "translated-text"
