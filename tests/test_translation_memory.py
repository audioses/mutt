"""Tests for translation_memory.TranslationMemory."""
from __future__ import annotations

from pathlib import Path

from translation_memory import TranslationMemory


def test_roundtrip_add_lookup(tmp_path: Path):
    tm = TranslationMemory(str(tmp_path / "tm.json"))
    tm.add_entry("hello", "merhaba", "en", "tr")
    assert tm.find_entry("hello", "en", "tr") == "merhaba"


def test_lookup_miss_returns_none(tmp_path: Path):
    tm = TranslationMemory(str(tmp_path / "tm.json"))
    assert tm.find_entry("nonexistent", "en", "tr") is None


def test_persistence_across_instances(tmp_path: Path):
    tm_path = tmp_path / "tm.json"
    a = TranslationMemory(str(tm_path))
    a.add_entry("hello", "merhaba", "en", "tr")
    b = TranslationMemory(str(tm_path))
    assert b.find_entry("hello", "en", "tr") == "merhaba"


def test_missing_file_initializes_empty(tmp_path: Path):
    tm = TranslationMemory(str(tmp_path / "missing.json"))
    assert tm.find_entry("anything", "en", "tr") is None
    assert tm.get_all_entries() == []


def test_language_pair_isolation(tmp_path: Path):
    tm = TranslationMemory(str(tmp_path / "tm.json"))
    tm.add_entry("hello", "merhaba", "en", "tr")
    # Same source, different target lang → should miss
    assert tm.find_entry("hello", "en", "es") is None


def test_clear_memory(tmp_path: Path):
    tm = TranslationMemory(str(tmp_path / "tm.json"))
    tm.add_entry("a", "b", "en", "tr")
    tm.clear_memory()
    assert tm.get_all_entries() == []


def test_delete_entry(tmp_path: Path):
    tm = TranslationMemory(str(tmp_path / "tm.json"))
    tm.add_entry("hello", "merhaba", "en", "tr")
    assert tm.delete_entry("hello", "merhaba", "en", "tr") is True
    assert tm.find_entry("hello", "en", "tr") is None
    # Deleting nonexistent returns False
    assert tm.delete_entry("hello", "merhaba", "en", "tr") is False
