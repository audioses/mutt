"""Translation progress statistics.

Pure, ``wx``-free logic so it can be unit-tested and reused. Counts are computed
against the full document with the same exclusion/ignore semantics used when
selecting entries for translation, so the "selected for translation" figure
here matches what the Translate button will actually process.
"""
from typing import Any, Iterable, Optional

from mutt.logic.entry_filter import is_entry_untranslated


def _word_count(text: str) -> int:
    return len((text or "").split())


def compute_translation_stats(
    all_entries: list,
    exclusion_manager: Optional[Any] = None,
    ignore_rules: Optional[Iterable[str]] = None,
) -> dict:
    """Return a dict of progress statistics for ``all_entries``.

    Keys:
        total, translated, untranslated, excluded,
        untranslated_selected (untranslated AND not excluded/ignored),
        source_words, untranslated_words (words in untranslated_selected),
        percent_complete (0-100).
    """
    ignore = {r for r in (ignore_rules or [])}
    total = len(all_entries)
    translated = 0
    untranslated = 0
    excluded = 0
    untranslated_selected = 0
    source_words = 0
    untranslated_words = 0

    for idx, entry in enumerate(all_entries):
        msgid = entry.get("msgid", "") or ""
        words = _word_count(msgid)
        source_words += words

        is_excluded = bool(
            exclusion_manager is not None
            and exclusion_manager.is_excluded_by_index(idx, all_entries)
        )
        is_ignored = bool(ignore) and msgid.strip() in ignore
        skipped = is_excluded or is_ignored
        if skipped:
            excluded += 1

        if is_entry_untranslated(entry):
            untranslated += 1
            if not skipped:
                untranslated_selected += 1
                untranslated_words += words
        else:
            translated += 1

    percent = (translated / total * 100.0) if total else 0.0
    return {
        "total": total,
        "translated": translated,
        "untranslated": untranslated,
        "excluded": excluded,
        "untranslated_selected": untranslated_selected,
        "source_words": source_words,
        "untranslated_words": untranslated_words,
        "percent_complete": percent,
    }


def format_stats_report(stats: dict) -> str:
    """Render stats as a human-readable, screen-reader-friendly block."""
    return (
        f"Total entries:            {stats['total']}\n"
        f"Translated:               {stats['translated']} "
        f"({stats['percent_complete']:.1f}%)\n"
        f"Untranslated:             {stats['untranslated']}\n"
        f"Excluded / ignored:       {stats['excluded']}\n"
        f"Untranslated & selected:  {stats['untranslated_selected']}\n"
        f"\n"
        f"Source words (total):     {stats['source_words']:,}\n"
        f"Words left to translate:  {stats['untranslated_words']:,}"
    )
