"""Ctrl+Backspace word-delete boundary (mutt.ui.utils)."""
from __future__ import annotations

from mutt.ui.utils import word_delete_start


def test_deletes_last_word():
    assert word_delete_start("hello world") == 6


def test_deletes_word_plus_trailing_space():
    assert word_delete_start("hello world ") == 6


def test_deletes_leading_whitespace_only():
    assert word_delete_start("   ") == 0


def test_nothing_before_cursor():
    assert word_delete_start("") == 0
