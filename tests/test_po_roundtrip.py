"""Round-trip regression tests for PO files.

These cover what a translator actually loses when the round-trip is lossy:
  * the project name/version in the header (Poedit's title bar)
  * translator comments (``#.``/``# `` lines)
  * plural forms (``msgstr[0]``, ``msgstr[1]``)

The path under test is the real one the app uses:
    file -> FormatManager.load -> legacy dicts -> FormatManager.save -> file
"""
from __future__ import annotations

import polib
import pytest

from format_handlers.base.manager import FormatManager
from format_handlers.compatibility import LegacyCompatibilityAdapter
from mutt.logic.entry_filter import is_entry_untranslated

SAMPLE = '''\
# Turkish translation for nvda.
msgid ""
msgstr ""
"Project-Id-Version: nvda\\n"
"POT-Creation-Date: 2026-01-01 10:00+0300\\n"
"Last-Translator: Someone <someone@example.com>\\n"
"Language-Team: Turkish\\n"
"Language: tr\\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"
"Plural-Forms: nplurals=2; plural=(n != 1);\\n"

#. Translators: use "sozcuk", never "kelime".
# my own note about this string
#: gui/settings.py:42
msgid "word"
msgstr ""

msgid "%d file"
msgid_plural "%d files"
msgstr[0] ""
msgstr[1] ""
'''


@pytest.fixture()
def po_path(tmp_path):
    path = tmp_path / "nvda.po"
    path.write_text(SAMPLE, encoding="utf-8")
    return path


def _round_trip(manager, po_path, out_path, mutate=None):
    """Load through the legacy bridge, optionally edit, save, reopen."""
    units, _ = manager.load_file(po_path)
    entries = LegacyCompatibilityAdapter.to_legacy_format(units)
    if mutate:
        mutate(entries)
    manager.save_file(
        LegacyCompatibilityAdapter.from_legacy_format(entries),
        out_path,
        source_path=po_path,
    )
    return entries, polib.pofile(str(out_path))


def test_header_and_metadata_are_preserved(po_path, tmp_path):
    _, saved = _round_trip(FormatManager(), po_path, tmp_path / "out.po")

    assert saved.metadata["Project-Id-Version"] == "nvda"
    assert saved.metadata["Language"] == "tr"
    assert saved.metadata["Plural-Forms"] == "nplurals=2; plural=(n != 1);"
    assert saved.metadata["Last-Translator"] == "Someone <someone@example.com>"
    assert "1.0" != saved.metadata["Project-Id-Version"], "must not be reset to a default"


def test_translator_comments_survive(po_path, tmp_path):
    entries, saved = _round_trip(FormatManager(), po_path, tmp_path / "out.po")

    # Visible to the UI...
    word = next(e for e in entries if e["msgid"] == "word")
    texts = [n["text"] for n in word["notes"]]
    assert any("sozcuk" in t for t in texts)
    assert any("my own note" in t for t in texts)

    # ...and still in the file afterwards.
    written = saved.find("word")
    assert "my own note" in written.tcomment
    assert "sozcuk" in written.comment


def test_plural_forms_survive_and_are_editable(po_path, tmp_path):
    def translate_plurals(entries):
        plural = next(e for e in entries if e.get("source_plural"))
        plural["target_plurals"] = {"0": "%d dosya", "1": "%d dosya"}

    entries, saved = _round_trip(
        FormatManager(), po_path, tmp_path / "out.po", mutate=translate_plurals
    )

    plural = next(e for e in entries if e.get("source_plural"))
    assert plural["source_plural"] == "%d files"

    written = saved.find("%d file")
    assert written.msgid_plural == "%d files"
    assert written.msgstr_plural == {0: "%d dosya", 1: "%d dosya"}


def test_untranslated_filter_counts_plural_forms(po_path):
    units, _ = FormatManager().load_file(po_path)
    entries = LegacyCompatibilityAdapter.to_legacy_format(units)
    plural = next(e for e in entries if e.get("source_plural"))

    assert is_entry_untranslated(plural), "empty msgstr[n] means untranslated"

    plural["target_plurals"] = {"0": "%d dosya", "1": ""}
    assert is_entry_untranslated(plural), "a half-filled plural still needs work"

    plural["target_plurals"] = {"0": "%d dosya", "1": "%d dosya"}
    assert not is_entry_untranslated(plural)
