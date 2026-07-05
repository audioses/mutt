"""Config file structure tests — ensures template stays in sync with what the
code reads from config.json."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "config.template.json"


@pytest.fixture
def template() -> dict:
    return json.loads(TEMPLATE.read_text(encoding="utf-8"))


def test_template_exists():
    assert TEMPLATE.exists(), "config.template.json is the canonical config shape"


def test_template_has_all_expected_providers(template):
    providers = template.get("providers", {})
    expected = {
        "OpenAI GPT",
        "OpenRouter",
        "Google Gemini",
        "HuggingFace",
        "Local Models",
        "Custom (OpenAI-Compatible)",
    }
    assert expected.issubset(providers.keys()), (
        f"Template missing providers: {expected - providers.keys()}"
    )


def test_custom_provider_has_base_url_field(template):
    custom = template["providers"]["Custom (OpenAI-Compatible)"]
    assert "base_url" in custom


def test_template_contains_no_real_api_keys(template):
    """Sanity: the template must never ship with real keys."""
    for name, provider in template.get("providers", {}).items():
        key = provider.get("api_key", "")
        assert key == "", f"Provider {name!r} has a leaked key in template: {key!r}"


def test_template_top_level_required_keys(template):
    required = {"providers", "prompts", "last_provider", "batch_size",
                "temperature", "max_tokens", "max_batch_tokens"}
    missing = required - template.keys()
    assert not missing, f"Template missing top-level keys: {missing}"
