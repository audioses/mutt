"""Plural-form helpers for legacy entry dicts.

A gettext entry with a plural has one source pair (``msgid`` /
``source_plural``) but N target forms (``target_plurals``), N depending on the
target language's ``Plural-Forms`` rule. The review UI edits one form at a
time; these helpers hide the string/int key mismatch that comes from JSON
round-trips (project files, autosave) where dict keys are always strings.
"""
from typing import Any, Dict, List, Optional

PLURAL_SOURCE_KEY = "source_plural"
PLURAL_TARGET_KEY = "target_plurals"


def is_plural(entry: Dict[str, Any]) -> bool:
    """True when this entry carries a msgid_plural."""
    return bool(entry.get(PLURAL_SOURCE_KEY))


def plural_forms(entry: Dict[str, Any]) -> List[int]:
    """Form indices for a plural entry, e.g. ``[0, 1]``. Empty if not plural.

    The count comes from the forms already present in the file (gettext writes
    one empty ``msgstr[n]`` per form even when untranslated). Falls back to two
    forms when the file gave us none.
    """
    if not is_plural(entry):
        return []
    raw = entry.get(PLURAL_TARGET_KEY) or {}
    indices = sorted(int(k) for k in raw.keys() if str(k).isdigit())
    return indices or [0, 1]


def form_label(form: int) -> str:
    return "Singular — msgstr[0]" if form == 0 else f"Plural {form} — msgstr[{form}]"


def source_for_form(entry: Dict[str, Any], form: Optional[int]) -> str:
    """Source text a given target form is translated from.

    gettext only ever has two source forms: form 0 renders the singular
    ``msgid``, every other form renders ``msgid_plural``.
    """
    if form is None or not is_plural(entry):
        return entry.get("msgid", "")
    return entry.get("msgid", "") if form == 0 else entry.get(PLURAL_SOURCE_KEY, "")


def target_for_form(entry: Dict[str, Any], form: Optional[int]) -> str:
    if form is None or not is_plural(entry):
        return entry.get("msgstr", "")
    raw = entry.get(PLURAL_TARGET_KEY) or {}
    return raw.get(str(form), raw.get(form, ""))


def set_target_for_form(entry: Dict[str, Any], form: Optional[int], text: str) -> None:
    """Write one target form back into the entry, in place."""
    if form is None or not is_plural(entry):
        entry["msgstr"] = text
        return
    raw = entry.get(PLURAL_TARGET_KEY)
    if not isinstance(raw, dict):
        raw = {}
    # Normalise to string keys so the entry stays JSON-round-trippable.
    normalised = {str(k): v for k, v in raw.items()}
    normalised[str(form)] = text
    entry[PLURAL_TARGET_KEY] = normalised


def demo() -> None:
    plain = {"msgid": "File", "msgstr": "Dosya"}
    assert plural_forms(plain) == []
    assert source_for_form(plain, None) == "File"
    set_target_for_form(plain, None, "Kütük")
    assert plain["msgstr"] == "Kütük"

    plural = {
        "msgid": "%d file",
        "source_plural": "%d files",
        "target_plurals": {0: "", 1: ""},  # int keys, as polib hands them over
    }
    assert plural_forms(plural) == [0, 1]
    assert source_for_form(plural, 0) == "%d file"
    assert source_for_form(plural, 1) == "%d files"
    set_target_for_form(plural, 1, "%d dosya")
    assert plural["target_plurals"] == {"0": "", "1": "%d dosya"}
    assert target_for_form(plural, 1) == "%d dosya"

    # Survives a JSON round-trip (project files / autosave)
    import json
    revived = json.loads(json.dumps(plural))
    assert plural_forms(revived) == [0, 1]
    assert target_for_form(revived, 1) == "%d dosya"

    # A plural entry with no forms recorded still offers the standard two
    assert plural_forms({"source_plural": "x"}) == [0, 1]
    print("plurals demo OK")


if __name__ == "__main__":
    demo()
