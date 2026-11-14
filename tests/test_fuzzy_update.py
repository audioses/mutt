"""Fuzzy entries: a translation whose source changed after it was made.

Covers the "Update fuzzy (outdated)" mode end to end: selecting them, sending
the old translation to the model as a starting point, clearing the flag once
updated, and the PO save honouring a cleared flag.
"""
import polib

from ai_translator import AITranslator
from format_handlers.base.manager import FormatManager
from format_handlers.compatibility import LegacyCompatibilityAdapter
from mutt.logic.entry_filter import select_entries_for_translation

FUZZY_PO = '''\
msgid ""
msgstr ""
"Content-Type: text/plain; charset=UTF-8\\n"

#, fuzzy
#| msgid "Save and quit"
msgid "Save and quit to menu"
msgstr "Kaydet ve çık"

msgid "road"
msgstr "yol"

msgid "empty"
msgstr ""
'''


def _entries(tmp_path):
    path = tmp_path / "in.po"
    path.write_text(FUZZY_PO, encoding="utf-8")
    units, _ = FormatManager().load_file(path)
    return path, LegacyCompatibilityAdapter.to_legacy_format(units)


def _save(entries, path, out):
    FormatManager().save_file(LegacyCompatibilityAdapter.from_legacy_format(entries), out, source_path=path)
    return polib.pofile(str(out))


def test_fuzzy_mode_selects_only_fuzzy_entries(tmp_path):
    _, entries = _entries(tmp_path)
    picked = select_entries_for_translation(entries, 2)
    assert [e["msgid"] for e in picked] == ["Save and quit to menu"]


def test_prompt_carries_old_translation_and_old_source(tmp_path):
    _, entries = _entries(tmp_path)
    fuzzy = select_entries_for_translation(entries, 2)
    t = AITranslator("OpenAI GPT", "key", "gpt-4")
    prompt = t._build_user_prompt([fuzzy[0]["msgid"]], "en", "tr", "", batch_entries=fuzzy)
    assert "Kaydet ve çık" in prompt
    assert 'old source "Save and quit"' in prompt
    assert "Update it" in prompt


def test_translated_entry_loses_fuzzy_untouched_one_keeps_it(monkeypatch):
    t = AITranslator("OpenAI GPT", "key", "gpt-4", batch_size=1)
    monkeypatch.setattr(t, "_initialize_client", lambda: None)
    monkeypatch.setattr("ai_translator.time.sleep", lambda *_: None)
    calls = {"n": 0}

    def fake_process(msgids, *a, **k):
        calls["n"] += 1
        return [f"T:{m}" for m in msgids], {"prompt_tokens": 1, "completion_tokens": 1}

    monkeypatch.setattr(t, "_process_batch", fake_process)
    entries = [{"msgid": "a", "msgstr": "old a", "fuzzy": True},
               {"msgid": "b", "msgstr": "old b", "fuzzy": True}]
    result, _ = t.translate_entries(entries, "en", "tr", cancel_check=lambda: calls["n"] >= 1)

    assert result[0] == {"msgid": "a", "msgstr": "T:a", "fuzzy": False}
    assert result[1]["fuzzy"] is True  # cancelled before it: still outdated


def test_cleared_fuzzy_stays_cleared_on_save(tmp_path):
    path, entries = _entries(tmp_path)
    entries[0]["fuzzy"] = False
    saved = _save(entries, path, tmp_path / "out.po")
    entry = saved.find("Save and quit to menu")
    assert "fuzzy" not in entry.flags
    assert not entry.previous_msgid


def test_untouched_fuzzy_keeps_flag_and_old_source(tmp_path):
    path, entries = _entries(tmp_path)
    saved = _save(entries, path, tmp_path / "out.po")
    entry = saved.find("Save and quit to menu")
    assert "fuzzy" in entry.flags
    assert entry.previous_msgid == "Save and quit"
