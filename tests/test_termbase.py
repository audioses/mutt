"""Termbase: TM lookups feed the prompt as advisory hints."""
from __future__ import annotations

from pathlib import Path

from ai_translator import AITranslator
from translation_memory import TranslationMemory


def test_find_matches_hits_terms_inside_a_sentence(tmp_path: Path):
    tm = TranslationMemory(str(tmp_path / "tm.json"))
    tm.add_entry("report usage", "kullanimi bildir", "en", "tr")
    tm.add_entry("unrelated term", "alakasiz", "en", "tr")
    matches = tm.find_matches(["Press enter to report usage now"], "en", "tr")
    assert matches == {"report usage": "kullanimi bildir"}


def test_find_matches_respects_language_pair(tmp_path: Path):
    tm = TranslationMemory(str(tmp_path / "tm.json"))
    tm.add_entry("report usage", "kullanimi bildir", "en", "tr")
    assert tm.find_matches(["report usage"], "en", "es") == {}


def test_prompt_includes_matching_terms_only():
    t = AITranslator("OpenAI GPT", "sk-abc", "gpt-4o-mini",
                     glossary={"report usage": "kullanimi bildir",
                               "unrelated term": "alakasiz"})
    prompt = t._build_user_prompt(["Press enter to report usage"], "en", "tr", None)
    assert '"report usage" -> "kullanimi bildir"' in prompt
    assert "alakasiz" not in prompt
    # Advisory, not mandatory — the model must be free to deviate by context.
    assert "override" in prompt


def test_prompt_unchanged_without_glossary():
    t = AITranslator("OpenAI GPT", "sk-abc", "gpt-4o-mini")
    prompt = t._build_user_prompt(["report usage"], "en", "tr", None)
    assert "Previously approved translations" not in prompt
