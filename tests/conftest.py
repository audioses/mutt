"""Shared pytest fixtures and project-root path setup.

All test modules run in a GUI-free environment. wx imports are stubbed where
they'd otherwise require a display. Network calls are mocked.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Put the project root on sys.path so tests can import top-level modules
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def sample_config() -> dict:
    """A minimal, in-memory config mirroring config.template.json."""
    return {
        "providers": {
            "OpenAI GPT": {"api_key": "sk-test", "api_model": "gpt-4o-mini"},
            "OpenRouter": {"api_key": "sk-or-test", "api_model": "anthropic/claude-3-haiku"},
            "Custom (OpenAI-Compatible)": {
                "api_key": "local-key",
                "api_model": "llama-3-8b",
                "base_url": "http://localhost:8080/v1",
            },
            "Google Gemini": {"api_key": "gg-test", "api_model": "gemini-1.5-flash"},
            "HuggingFace": {"api_key": "", "api_model": "Helsinki-NLP/opus-mt", "device": "cpu"},
            "Local Models": {"api_key": "", "api_model": "local-model"},
            "Argos Translate": {"api_key": "", "api_model": ""},
        },
        "last_provider": "OpenAI GPT",
        "batch_size": 5,
        "local_backend": "Llama.cpp",
        "temperature": 0.1,
        "max_batch_tokens": 4000,
        "enable_surrounding_context": False,
        "prompts": [],
    }


@pytest.fixture
def sample_po_entries() -> list:
    """A small PO entry list shaped like what polib + app.py produces."""
    return [
        {"msgid": "Hello, world!", "msgstr": "", "obsolete": False},
        {"msgid": "Goodbye", "msgstr": "", "obsolete": False},
        {"msgid": "Stale key", "msgstr": "eski", "obsolete": True},
    ]


@pytest.fixture
def tmp_config_file(tmp_path: Path, sample_config: dict) -> Path:
    """Writes sample_config to a tmp file and returns its path."""
    p = tmp_path / "config.json"
    p.write_text(json.dumps(sample_config), encoding="utf-8")
    return p


class _FakeOpenAIMessage:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeOpenAIChoice:
    def __init__(self, content: str) -> None:
        self.message = _FakeOpenAIMessage(content)


class _FakeOpenAIUsage:
    def __init__(self, prompt: int = 10, completion: int = 20) -> None:
        self.prompt_tokens = prompt
        self.completion_tokens = completion


class FakeOpenAIResponse:
    """Minimal stand-in for an openai ChatCompletion response."""

    def __init__(self, content: str = "translated-text", prompt_tokens: int = 10,
                 completion_tokens: int = 20) -> None:
        self.choices = [_FakeOpenAIChoice(content)]
        self.usage = _FakeOpenAIUsage(prompt_tokens, completion_tokens)


class FakeOpenAIClient:
    """Drop-in fake for openai.OpenAI() — records calls for assertions."""

    def __init__(self, *, api_key: str | None = None, base_url: str | None = None) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.calls: list[dict] = []

        class _Completions:
            def __init__(outer) -> None:
                outer._parent = self

            def create(outer, **kwargs):  # noqa: N805 - keep parity with openai shape
                outer._parent.calls.append(kwargs)
                return FakeOpenAIResponse()

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()
        self.models = _FakeModelsList()


class _FakeModel:
    def __init__(self, model_id: str) -> None:
        self.id = model_id


class _FakeModelsList:
    def list(self):
        return [_FakeModel("gpt-4o"), _FakeModel("gpt-4o-mini"), _FakeModel("llama-3-8b")]


@pytest.fixture(autouse=True)
def _silence_response_log(monkeypatch):
    """Prevent tests from writing to the real openai_responses.log file."""
    try:
        import ai_translator  # type: ignore

        monkeypatch.setattr(ai_translator, "_log_raw_response", lambda *_a, **_k: None)
    except Exception:
        pass


@pytest.fixture
def fake_openai(monkeypatch):
    """Patches `openai.OpenAI` to return a FakeOpenAIClient. Returns a factory
    so tests can assert on the constructed client."""
    constructed: list[FakeOpenAIClient] = []

    def _factory(api_key=None, base_url=None, **kwargs):
        c = FakeOpenAIClient(api_key=api_key, base_url=base_url)
        constructed.append(c)
        return c

    import openai  # type: ignore

    monkeypatch.setattr(openai, "OpenAI", _factory)
    return constructed
