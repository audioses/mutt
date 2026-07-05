"""Unit tests for mutt.api_helper.APIHelper."""
from __future__ import annotations

from mutt.api_helper import APIHelper


def test_get_custom_openai_models_empty_base_url_returns_empty():
    assert APIHelper.get_custom_openai_models("k", "") == []
    assert APIHelper.get_custom_openai_models("k", None) == []


def test_get_custom_openai_models_uses_base_url(fake_openai):
    models = APIHelper.get_custom_openai_models("some-key", "http://localhost:8080/v1")
    assert set(models) == {"gpt-4o", "gpt-4o-mini", "llama-3-8b"}
    # Sorted alphabetically
    assert models == sorted(models)
    assert fake_openai[0].base_url == "http://localhost:8080/v1"
    assert fake_openai[0].api_key == "some-key"


def test_get_custom_openai_models_blank_key_uses_placeholder(fake_openai):
    APIHelper.get_custom_openai_models("", "http://x/v1")
    assert fake_openai[0].api_key == "not-needed"


def test_get_custom_openai_models_swallows_network_errors(monkeypatch):
    def _boom(*a, **kw):
        raise ConnectionError("dns failure")
    import openai
    monkeypatch.setattr(openai, "OpenAI", _boom)
    # Must return [] rather than propagating
    assert APIHelper.get_custom_openai_models("k", "http://bad/v1") == []
