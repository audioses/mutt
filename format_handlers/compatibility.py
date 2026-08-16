"""
Compatibility adapter for bridging the new TranslationUnit format with the
existing legacy dictionary format used in the MUTT application.
"""

from typing import List, Dict, Any
from .base.translation_unit import TranslationUnit, TranslationStatus, Note

# Keys the adapter owns explicitly; everything else on a legacy dict is
# round-tripped through ``TranslationUnit.attributes``.
_RESERVED_KEYS = ("msgid", "msgstr", "msgctxt", "fuzzy", "unit_id", "notes")

class LegacyCompatibilityAdapter:
    """
    A stateless adapter to convert between the new TranslationUnit objects and the
    legacy dictionary format, ensuring backward compatibility with the main application.
    
    The legacy format is a simple dictionary, typically with keys like "msgid",
    "msgstr", "msgctxt", and "fuzzy".
    """

    @staticmethod
    def to_legacy_format(translation_units: List[TranslationUnit]) -> List[Dict[str, Any]]:
        """
        Convert a list of TranslationUnit objects to a list of legacy format dictionaries.

        Args:
            translation_units: A list of TranslationUnit objects to be converted.

        Returns:
            A list of dictionaries representing the translation units in the legacy format.
        """
        return [LegacyCompatibilityAdapter.create_legacy_entry(unit) for unit in translation_units]

    @staticmethod
    def from_legacy_format(legacy_entries: List[Dict[str, Any]]) -> List[TranslationUnit]:
        """
        Convert a list of legacy format dictionaries to a list of TranslationUnit objects.

        Args:
            legacy_entries: A list of dictionaries in the legacy format.

        Returns:
            A list of TranslationUnit objects populated with data from the legacy entries.
        """
        units = []
        for legacy_entry in legacy_entries:
            unit = TranslationUnit()
            unit.source = legacy_entry.get("msgid", "")
            unit.target = legacy_entry.get("msgstr", "")
            unit.context = legacy_entry.get("msgctxt", "")
            unit.id = legacy_entry.get("unit_id", "")

            if legacy_entry.get("fuzzy"):
                unit.fuzzy = True
                unit.status = TranslationStatus.NEEDS_WORK
            elif unit.target:
                unit.status = TranslationStatus.TRANSLATED
            else:
                unit.status = TranslationStatus.NEW

            # Store other potential polib-specific fields in attributes
            for key, value in legacy_entry.items():
                if key not in _RESERVED_KEYS:
                    unit.attributes[key] = value

            # Translator/extractor comments live in ``notes``, not attributes.
            # Without this the round-trip silently deleted every comment in the
            # file (see po_handler.save, which rebuilds tcomment/comment from
            # unit.notes).
            for note_data in legacy_entry.get("notes") or []:
                try:
                    unit.notes.append(Note.from_dict(note_data))
                except Exception:  # noqa: BLE001 - skip malformed note, keep the rest
                    continue

            units.append(unit)
        return units

    @staticmethod
    def update_legacy_entry(legacy_entry: Dict[str, Any], translation_unit: TranslationUnit) -> None:
        """
        Update a legacy format dictionary with data from a TranslationUnit object.

        Args:
            legacy_entry: The dictionary to be updated.
            translation_unit: The TranslationUnit object containing the new data.
        """
        legacy_entry["msgid"] = translation_unit.source
        legacy_entry["msgstr"] = translation_unit.target
        legacy_entry["msgctxt"] = translation_unit.context
        legacy_entry["fuzzy"] = translation_unit.fuzzy or translation_unit.status == TranslationStatus.NEEDS_WORK

        # Update any other attributes stored on the unit
        legacy_entry.update(translation_unit.attributes)
        legacy_entry["notes"] = [note.to_dict() for note in translation_unit.notes]

    @staticmethod
    def create_legacy_entry(translation_unit: TranslationUnit) -> Dict[str, Any]:
        """
        Create a new legacy format dictionary from a TranslationUnit object.

        Args:
            translation_unit: The TranslationUnit object to convert.

        Returns:
            A dictionary representing the translation unit in the legacy format.
        """
        legacy_entry = {
            "msgid": translation_unit.source,
            "msgstr": translation_unit.target,
            "msgctxt": translation_unit.context,
            "fuzzy": translation_unit.fuzzy or translation_unit.status == TranslationStatus.NEEDS_WORK,
            "unit_id": translation_unit.id
        }
        # Preserve other format-specific fields
        legacy_entry.update(translation_unit.attributes)
        # Comments must survive the trip to the UI and back — they are what
        # tells a translator *why* a string reads the way it does, and dropping
        # them here used to erase them from the saved file.
        legacy_entry["notes"] = [note.to_dict() for note in translation_unit.notes]
        return legacy_entry