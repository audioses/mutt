"""Pure entry-selection logic for translation filtering.

Deliberately free of any ``wx`` dependency so it can be unit-tested and reused.

The critical invariant fixed here: sectional exclusion rules are expressed as
indices into the *full* entry list (``all_entries``). They MUST therefore be
evaluated against each entry's original index — never against an already
filtered subset (e.g. "untranslated only"), or the rule indices line up with
the wrong entries and completely unrelated strings get excluded/kept.
"""
from typing import Any, Iterable, Optional, Protocol


class _ExclusionLike(Protocol):
    def is_excluded_by_index(self, index: int, all_entries: Any) -> bool: ...


def is_entry_untranslated(entry: dict) -> bool:
    """An entry counts as untranslated when its target is empty.

    A target identical to the source used to count as untranslated too, as a
    "not yet touched" sentinel. It cost more than it bought: song titles,
    proper nouns and product names are legitimately the same in both
    languages, so they were re-sent to the model on every run, came back
    unchanged, and were selected again - 541 of them in one 9,261-string
    file, forever. Like gettext itself, a filled target is now a translation.

    Plural entries carry their targets in ``target_plurals`` (msgstr[n]) and
    leave ``msgstr`` empty, so they are judged on those forms instead: any
    empty form means the entry still needs work, which is how gettext itself
    counts them."""
    if entry.get("source_plural"):
        forms = entry.get("target_plurals") or {}
        if not forms:
            return True
        return any(not (text or "").strip() for text in forms.values())
    return not (entry.get("msgstr") or "").strip()


def select_entries_for_translation(
    all_entries: list,
    mode: int,
    ignore_rules: Optional[Iterable[str]] = None,
    exclusion_manager: Optional[_ExclusionLike] = None,
) -> list:
    """Return the sublist of ``all_entries`` that should be translated.

    Args:
        all_entries: the complete, in-order list of entries for the document.
        mode: ``0`` selects only untranslated entries; any other value selects
            all entries.
        ignore_rules: optional iterable of source strings (msgids) to skip,
            from a file-based ignore list.
        exclusion_manager: optional object exposing
            ``is_excluded_by_index(index, all_entries)``. Evaluated against the
            entry's ORIGINAL index in ``all_entries`` so sectional rules stay
            correct regardless of the untranslated/ignore filtering applied.
    """
    ignore = {r for r in (ignore_rules or [])}
    selected = []
    for original_idx, entry in enumerate(all_entries):
        if mode == 0 and not is_entry_untranslated(entry):
            continue
        if ignore and (entry.get("msgid", "") or "").strip() in ignore:
            continue
        if exclusion_manager is not None and exclusion_manager.is_excluded_by_index(
            original_idx, all_entries
        ):
            continue
        selected.append(entry)
    return selected


def _merge_key(entry: dict):
    """Address an entry for merging: the handler-assigned ``unit_id`` when the
    entry has one, else the source string + context (older project files
    predate ``unit_id``)."""
    uid = entry.get("unit_id")
    if uid not in (None, ""):
        return ("id", uid)
    return ("src", entry.get("msgctxt") or "", entry.get("msgid") or "")


def merge_reviewed_entries(all_entries: list, reviewed: list) -> list:
    """Overlay the reviewed/translated entries back onto the full document.

    "Translate untranslated" hands the translator a *subset* of the document.
    Saving that subset on its own deleted every entry the filter had skipped:
    a 9,261-string PO came back with 7,743, losing all 1,518 already-translated
    and fuzzy strings. Entries are matched by :func:`_merge_key`, which
    survives the TranslationUnit <-> legacy-dict bridge and the JSON round-trip
    through project/autosave files. An entry that matches nothing is appended
    rather than dropped - a translation we hold is never thrown away.
    """
    if not all_entries:
        return list(reviewed)
    merged = list(all_entries)
    slots: dict = {}
    for i, entry in enumerate(merged):
        slots.setdefault(_merge_key(entry), []).append(i)
    appended = []
    for entry in reviewed:
        free = slots.get(_merge_key(entry))
        if free:
            merged[free.pop(0)] = entry
        else:
            appended.append(entry)
    return merged + appended
