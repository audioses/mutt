"""A long batch the model garbles must still translate: repair the response
when it can be repaired, otherwise halve the batch and retry."""
from __future__ import annotations

import json

import pytest

from ai_translator import AITranslator



def _translator(monkeypatch):
    t = AITranslator("OpenAI GPT", "key", "gpt-4", batch_size=10)
    monkeypatch.setattr(t, "_initialize_client", lambda: None)
    monkeypatch.setattr("ai_translator.time.sleep", lambda *_a, **_k: None)
    return t


def test_repairs_raw_newline_inside_a_string():
    broken = '{"translated_texts": ["bir\niki", "üç"]}'
    with pytest.raises(json.JSONDecodeError):
        json.loads(broken)
    fixed = json.loads(AITranslator._repair_model_json(broken))
    assert fixed["translated_texts"] == ["bir\niki", "üç"]


def test_repairs_stray_dot_between_elements():
    broken = '{"translated_texts": ["bir",. "iki"]}'
    fixed = json.loads(AITranslator._repair_model_json(broken))
    assert fixed["translated_texts"] == ["bir", "iki"]


def test_repair_leaves_punctuation_inside_a_translation_alone():
    good = '{"translated_texts": ["Dur, . sonra git", "bitti;"]}'
    assert json.loads(AITranslator._repair_model_json(good)) == json.loads(good)


def test_unparsable_batch_is_halved_and_retried(monkeypatch):
    t = _translator(monkeypatch)
    calls = []

    def fake_once(texts, src, tgt, context, window=None, batch_entries=None):
        calls.append(list(texts))
        if len(texts) > 2:
            raise ValueError("Failed to extract JSON from model response: boom")
        return [f"T:{m}" for m in texts], {"prompt_tokens": 1, "completion_tokens": 1}

    monkeypatch.setattr(t, "_process_batch_once", fake_once)
    out, usage = t._process_batch(["a", "b", "c", "d"], "en", "tr", "")

    assert out == ["T:a", "T:b", "T:c", "T:d"]
    assert calls[0] == ["a", "b", "c", "d"]
    assert usage["prompt_tokens"] == 2


def test_fatal_errors_are_not_retried(monkeypatch):
    t = _translator(monkeypatch)
    calls = []

    def fake_once(texts, *a, **k):
        calls.append(list(texts))
        raise ValueError("Incorrect API key provided")

    monkeypatch.setattr(t, "_process_batch_once", fake_once)
    with pytest.raises(ValueError):
        t._process_batch(["a", "b", "c", "d"], "en", "tr", "")
    assert len(calls) == 1


def test_splitting_gives_up_instead_of_descending_forever(monkeypatch):
    t = _translator(monkeypatch)
    calls = []

    def fake_once(texts, *a, **k):
        calls.append(list(texts))
        raise ValueError("AI returned a malformed list. Expected 9, but got 2.")

    monkeypatch.setattr(t, "_process_batch_once", fake_once)
    with pytest.raises(ValueError):
        t._process_batch([str(i) for i in range(64)], "en", "tr", "")
    assert len(calls) <= 2 ** (t._MAX_BATCH_SPLITS + 1)


def test_batch_size_is_honoured_as_configured():
    # No ceiling any more: an oversized batch is halved on failure instead.
    t = AITranslator("OpenAI GPT", "key", "gpt-4", batch_size=5000)
    assert t.batch_size == 5000
    assert AITranslator("OpenAI GPT", "key", "gpt-4", batch_size=0).batch_size == 1
    assert AITranslator("OpenAI GPT", "key", "gpt-4", batch_size=50).batch_size == 50


def test_truncated_reply_is_halved_not_fatal(monkeypatch):
    """With no batch ceiling, the likeliest failure is a reply cut off at the
    model's output limit. It used to match no split marker and kill the run."""
    t = _translator(monkeypatch)
    calls = []

    def fake_once(texts, *a, **k):
        calls.append(len(texts))
        if len(texts) > 2:
            # Exactly what _check_finish_reason raises, wrapped the way
            # _process_batch_once re-raises it.
            raise ValueError(
                "Batch processing failed due to a critical error: Model truncated "
                "its response because it hit an output-token limit. Your batch is "
                "too large for this model's default output budget."
            )
        return [f"T:{m}" for m in texts], {"prompt_tokens": 1, "completion_tokens": 1}

    monkeypatch.setattr(t, "_process_batch_once", fake_once)
    out, _ = t._process_batch(list("abcdefgh"), "en", "tr", "")

    assert out == [f"T:{c}" for c in "abcdefgh"]
    assert calls[0] == 8  # tried whole first, then halved down to size

