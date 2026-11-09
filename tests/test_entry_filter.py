"""Regression tests for translation entry selection.

The headline bug: in "Translate untranslated" mode, sectional exclusion rules
isolated the wrong text. Rules are indexed against the FULL document, but the
old code applied them positionally to the already-untranslated-filtered subset,
so they dropped unrelated strings. These tests lock in the corrected behaviour
using the reporter's NVDA "what's new" scenario.
"""
import pytest

from exprules import ExclusionManager
from mutt.logic.entry_filter import (
    is_entry_untranslated,
    merge_reviewed_entries,
    select_entries_for_translation,
)


def _entry(msgid, translated=False):
    return {"msgid": msgid, "msgstr": ("translated" if translated else "")}


@pytest.fixture
def nvda_doc():
    # A document with translated and untranslated entries scattered throughout,
    # mirroring the bug report. Two exclusion rules wrap a middle band of
    # security-patch notes that should be the only thing left to translate.
    return [
        _entry("What's new in NVDA"),                        # 0  rule1 start
        _entry("2026.1 feature A"),                          # 1  untranslated, excluded
        _entry("2026.1 feature B", translated=True),         # 2
        _entry("2026.1 feature C"),                          # 3  untranslated, excluded
        _entry("2026.1 dev change 1", translated=True),      # 4
        _entry("2026.1 dev change 2"),                       # 5  untranslated, excluded
        _entry("2026.1 changes for developers"),             # 6  rule1 end
        _entry("Security patch 2025.4.1"),                   # 7  TARGET (untranslated)
        _entry("Security fix detail"),                       # 8  TARGET (untranslated)
        _entry("Security patch 2025.4.2", translated=True),  # 9  already translated
        _entry("2025.3"),                                    # 10 rule2 start
        _entry("old feature", ),                             # 11 untranslated, excluded
        _entry("old feature 2", translated=True),            # 12
    ]


@pytest.fixture
def two_rules():
    mgr = ExclusionManager()
    mgr.add_rule(0, 6)    # whole "what's new ... developers" block
    mgr.add_rule(10, -1)  # 2025.3 to end of file
    return mgr


def test_untranslated_mode_isolates_target_band(nvda_doc, two_rules):
    selected = select_entries_for_translation(nvda_doc, 0, None, two_rules)
    msgids = [e["msgid"] for e in selected]
    # Exactly the untranslated security-patch notes between the two rules —
    # nothing from the excluded ranges, despite those holding untranslated rows.
    assert msgids == ["Security patch 2025.4.1", "Security fix detail"]


def test_untranslated_mode_excludes_all_rule_ranges(nvda_doc, two_rules):
    selected = select_entries_for_translation(nvda_doc, 0, None, two_rules)
    excluded_msgids = {
        "2026.1 feature A", "2026.1 feature C", "2026.1 dev change 2", "old feature",
    }
    assert not (excluded_msgids & {e["msgid"] for e in selected})


def test_all_mode_keeps_translated_in_band(nvda_doc, two_rules):
    # "Translate all" keeps the already-translated entry in the un-excluded band.
    selected = select_entries_for_translation(nvda_doc, 1, None, two_rules)
    assert [e["msgid"] for e in selected] == [
        "Security patch 2025.4.1",
        "Security fix detail",
        "Security patch 2025.4.2",
    ]


def test_no_rules_returns_untranslated_only(nvda_doc):
    selected = select_entries_for_translation(nvda_doc, 0, None, ExclusionManager())
    assert all(is_entry_untranslated(e) for e in selected)
    # Untranslated indices with no rules: 0,1,3,5,6,7,8,10,11 (headings count too).
    assert len(selected) == 9


def test_ignore_rules_also_indexed_against_full_doc(nvda_doc, two_rules):
    ignore = ["Security fix detail"]
    selected = select_entries_for_translation(nvda_doc, 0, ignore, two_rules)
    assert [e["msgid"] for e in selected] == ["Security patch 2025.4.1"]


def test_is_entry_untranslated_handles_msgid_equals_msgstr():
    assert is_entry_untranslated({"msgid": "a", "msgstr": "a"})
    assert is_entry_untranslated({"msgid": "a", "msgstr": ""})
    assert is_entry_untranslated({"msgid": "a", "msgstr": None})
    assert not is_entry_untranslated({"msgid": "a", "msgstr": "b"})


# --------------------------------------------------------------- merge-back
# The second half of the same bug: "Translate untranslated" filters the
# document, and saving the filtered subset deleted everything it skipped.


def _doc():
    return [
        {"unit_id": "0", "msgid": "a", "msgstr": "A"},      # already translated
        {"unit_id": "1", "msgid": "b", "msgstr": ""},       # selected
        {"unit_id": "2", "msgid": "c", "msgstr": "C", "fuzzy": True},
        {"unit_id": "3", "msgid": "d", "msgstr": ""},       # selected
    ]


def test_merge_keeps_the_whole_document():
    doc = _doc()
    selected = select_entries_for_translation(doc, 0)
    assert [e["msgid"] for e in selected] == ["b", "d"]
    reviewed = [dict(e, msgstr=e["msgid"].upper()) for e in selected]

    merged = merge_reviewed_entries(doc, reviewed)

    assert [e["msgid"] for e in merged] == ["a", "b", "c", "d"]
    assert [e["msgstr"] for e in merged] == ["A", "B", "C", "D"]
    assert merged[2]["fuzzy"] is True  # untouched entries keep their flags


def test_merge_of_a_partial_review_leaves_the_rest_as_it_was():
    doc = _doc()
    reviewed = [dict(doc[1], msgstr="B")]  # only the first reviewed entry
    merged = merge_reviewed_entries(doc, reviewed)
    assert [e["msgstr"] for e in merged] == ["A", "B", "C", ""]


def test_merge_never_drops_an_entry_it_cannot_place():
    merged = merge_reviewed_entries(_doc(), [{"unit_id": "99", "msgid": "z", "msgstr": "Z"}])
    assert len(merged) == 5
    assert merged[-1]["msgid"] == "z"


def test_merge_falls_back_to_the_source_string_without_unit_ids():
    doc = [{"msgid": "a", "msgstr": "A"}, {"msgid": "b", "msgstr": ""}]
    merged = merge_reviewed_entries(doc, [{"msgid": "b", "msgstr": "B"}])
    assert [e["msgstr"] for e in merged] == ["A", "B"]
