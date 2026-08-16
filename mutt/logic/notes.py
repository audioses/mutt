"""Rendering of per-entry comments (translator notes, extracted comments,
source references).

Comments arrive as a list of serialised ``Note`` dicts on each legacy entry
(see ``format_handlers.compatibility``). Two consumers share this module: the
review panel, which shows them to the translator, and the AI prompt builder,
which sends them to the model as translation guidance.
"""
from typing import Any, Dict, List

_LABELS = {
    "translator": "Translator comment",
    "extractor": "Extracted comment",
    "reference": "Reference",
}


def _notes(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = entry.get("notes")
    return [n for n in raw if isinstance(n, dict) and n.get("text")] if isinstance(raw, list) else []


def format_entry_notes(entry: Dict[str, Any]) -> str:
    """Human-readable block for the review panel. Empty-ish entries get a
    spoken placeholder rather than a blank field."""
    lines = []
    for note in _notes(entry):
        label = _LABELS.get(note.get("author", ""), "Note")
        text = note["text"]
        if label == "Reference":
            # Already carries its own "Reference: " prefix from the PO handler.
            lines.append(text)
        else:
            lines.append(f"{label}: {text}")
    context = entry.get("msgctxt")
    if context:
        lines.insert(0, f"Context (msgctxt): {context}")
    return "\n".join(lines) if lines else "(no comments for this entry)"


def guidance_notes(entry: Dict[str, Any]) -> str:
    """Just the parts worth spending tokens on when prompting a model:
    translator and extractor comments. Source-file references are noise."""
    parts = [
        note["text"].strip()
        for note in _notes(entry)
        if note.get("author") in ("translator", "extractor")
    ]
    context = entry.get("msgctxt")
    if context:
        parts.insert(0, f"context: {context}")
    return " | ".join(p for p in parts if p)


def demo() -> None:
    entry = {
        "msgid": "word",
        "msgctxt": "grammar",
        "notes": [
            {"text": "Translate as 'sözcük', not 'kelime'.", "author": "translator"},
            {"text": "Label of the word count button", "author": "extractor"},
            {"text": "Reference: gui/settings.py:42", "author": "reference"},
            {"text": "", "author": "translator"},  # dropped: no text
            "not a dict",                            # dropped: malformed
        ],
    }
    rendered = format_entry_notes(entry)
    assert "Context (msgctxt): grammar" in rendered
    assert "Translator comment: Translate as 'sözcük', not 'kelime'." in rendered
    assert "Extracted comment: Label of the word count button" in rendered
    assert "Reference: gui/settings.py:42" in rendered

    guidance = guidance_notes(entry)
    assert "sözcük" in guidance
    assert "settings.py" not in guidance, "references must not reach the prompt"

    assert format_entry_notes({"msgid": "x"}) == "(no comments for this entry)"
    assert guidance_notes({"msgid": "x"}) == ""
    print("notes demo OK")


if __name__ == "__main__":
    demo()
