"""Tests for translation progress statistics."""
from exprules import ExclusionManager
from mutt.logic.stats import compute_translation_stats, format_stats_report


def _entry(msgid, translated=False):
    return {"msgid": msgid, "msgstr": ("done" if translated else "")}


def test_basic_counts():
    entries = [
        _entry("one two three"),            # untranslated, 3 words
        _entry("four five", translated=True),
        _entry("six"),                       # untranslated, 1 word
    ]
    stats = compute_translation_stats(entries)
    assert stats["total"] == 3
    assert stats["translated"] == 1
    assert stats["untranslated"] == 2
    assert stats["excluded"] == 0
    assert stats["untranslated_selected"] == 2
    assert stats["source_words"] == 6
    assert stats["untranslated_words"] == 4
    assert round(stats["percent_complete"], 1) == 33.3


def test_excluded_entries_not_counted_as_selected():
    entries = [_entry("a b"), _entry("c d"), _entry("e f")]
    mgr = ExclusionManager()
    mgr.add_rule(0, 0)  # exclude first entry
    stats = compute_translation_stats(entries, mgr)
    assert stats["excluded"] == 1
    assert stats["untranslated"] == 3
    assert stats["untranslated_selected"] == 2
    assert stats["untranslated_words"] == 4  # only the two selected entries


def test_ignore_rules_count_as_excluded():
    entries = [_entry("skip me"), _entry("keep me")]
    stats = compute_translation_stats(entries, None, ignore_rules=["skip me"])
    assert stats["excluded"] == 1
    assert stats["untranslated_selected"] == 1


def test_empty_document():
    stats = compute_translation_stats([])
    assert stats["total"] == 0
    assert stats["percent_complete"] == 0.0


def test_format_report_contains_key_figures():
    stats = compute_translation_stats([_entry("a"), _entry("b", translated=True)])
    report = format_stats_report(stats)
    assert "Total entries" in report
    assert "Words left to translate" in report
