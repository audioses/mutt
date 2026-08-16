"""Plural entries must be translated per msgstr[n], and per-entry comments
must reach the model."""
from __future__ import annotations

from ai_translator import AITranslator


def _translator(monkeypatch, batch_size=10):
    t = AITranslator("OpenAI GPT", "key", "gpt-4", batch_size=batch_size)
    monkeypatch.setattr(t, "_initialize_client", lambda: None)
    monkeypatch.setattr("ai_translator.time.sleep", lambda *_a, **_k: None)
    seen = []

    def fake_process(texts, src, tgt, context, window, batch_entries=None):
        seen.append({"texts": list(texts), "entries": list(batch_entries or [])})
        return [f"T:{m}" for m in texts], {"prompt_tokens": 0, "completion_tokens": 0}

    monkeypatch.setattr(t, "_process_batch", fake_process)
    return t, seen


def test_plural_entry_sends_both_source_forms(monkeypatch):
    t, seen = _translator(monkeypatch)
    entries = [
        {"msgid": "Save", "msgstr": ""},
        {"msgid": "%d file", "source_plural": "%d files",
         "msgstr": "", "target_plurals": {"0": "", "1": ""}},
    ]

    result, _ = t.translate_entries(entries, "en", "tr")

    # Singular and plural source both went to the model.
    assert seen[0]["texts"] == ["Save", "%d file", "%d files"]
    # ...and came back into the right msgstr[n], not into msgstr.
    assert result[0]["msgstr"] == "T:Save"
    assert result[1]["target_plurals"] == {"0": "T:%d file", "1": "T:%d files"}


def test_three_form_language_seeds_every_plural_form(monkeypatch):
    t, _ = _translator(monkeypatch)
    entries = [{"msgid": "%d file", "source_plural": "%d files",
                "msgstr": "", "target_plurals": {"0": "", "1": "", "2": ""}}]

    result, _ = t.translate_entries(entries, "en", "pl")

    assert result[0]["target_plurals"] == {
        "0": "T:%d file", "1": "T:%d files", "2": "T:%d files",
    }


def test_entry_comments_reach_the_prompt(monkeypatch):
    t, _ = _translator(monkeypatch)
    entry = {
        "msgid": "word", "msgstr": "",
        "notes": [{"text": "Translate as 'sozcuk'.", "author": "translator"},
                  {"text": "Reference: gui.py:1", "author": "reference"}],
    }

    prompt = t._build_user_prompt(["word"], "en", "tr", None, batch_entries=[entry])

    assert "Item 0" in prompt
    assert "sozcuk" in prompt
    assert "gui.py" not in prompt, "file references are noise, not guidance"


def test_original_entries_are_not_mutated(monkeypatch):
    t, _ = _translator(monkeypatch)
    original_plurals = {"0": "", "1": ""}
    entries = [{"msgid": "%d file", "source_plural": "%d files",
                "msgstr": "", "target_plurals": original_plurals}]

    t.translate_entries(entries, "en", "tr")

    assert original_plurals == {"0": "", "1": ""}, "input must be left untouched"
