"""
Format handler for GNU Gettext PO and POT files.
"""

import polib
from pathlib import Path
from typing import List, Dict, Any

from ..base.format_handler import FormatHandler, FormatCapabilities, ValidationResult, FormatHandlerError
from ..base.translation_unit import TranslationUnit, TranslationStatus, Note, NoteType


class POHandler(FormatHandler):
    """
    Handles reading and writing of .po and .pot (template) files.

    This handler uses the 'polib' library to parse and serialize Gettext files,
    mapping them to the universal TranslationUnit model.
    """

    @property
    def format_name(self) -> str:
        return "GNU Gettext PO"

    @property
    def file_extensions(self) -> List[str]:
        return [".po", ".pot"]

    @property
    def mime_types(self) -> List[str]:
        return ["text/x-gettext-translation", "text/x-gettext-translation-template"]

    @property
    def format_capabilities(self) -> FormatCapabilities:
        """
        Defines the features supported by the PO format.
        """
        caps = FormatCapabilities()
        caps.supports_comments = True
        caps.supports_context = True
        caps.supports_plural_forms = True
        caps.supports_fuzzy_matching = True
        caps.supports_translation_status = True
        caps.supports_review_workflow = False  # PO format itself doesn't have a review status
        caps.supports_file_metadata = True
        caps.supports_attributes = True
        caps.preserves_structure = True
        return caps

    def can_handle(self, file_path: Path, content_sample: bytes = None) -> bool:
        """
        Determines if this handler can process the given file.
        It checks the file extension and can optionally check file content.
        """
        if file_path.suffix.lower() in self.file_extensions:
            if content_sample:
                # A simple check for common PO file content
                try:
                    content_str = content_sample.decode('utf-8')
                    return 'msgid ""' in content_str or 'msgid ' in content_str
                except UnicodeDecodeError:
                    return False
            return True
        return False

    def load(self, file_path: Path, **options) -> List[TranslationUnit]:
        """
        Load translation units from a .po or .pot file.
        """
        try:
            po_file = polib.pofile(str(file_path), **options)
        except (PermissionError, IOError, Exception) as e:
            # polib.pofile can raise different exceptions (e.g., IOError, UnicodeDecodeError, etc.)
            # We wrap them in FormatHandlerError for consistency.
            raise FormatHandlerError(f"Failed to parse PO file: {e}") from e

        units = []
        for i, entry in enumerate(po_file):
            if entry.obsolete:
                continue

            unit = TranslationUnit()
            unit.id = str(i)
            unit.source = entry.msgid
            unit.target = entry.msgstr
            unit.context = entry.msgctxt
            unit.fuzzy = 'fuzzy' in entry.flags

            # Map status
            if unit.fuzzy:
                unit.status = TranslationStatus.NEEDS_WORK
            elif entry.translated():
                unit.status = TranslationStatus.TRANSLATED
            else:
                unit.status = TranslationStatus.NEW

            # Comments
            if entry.tcomment:
                unit.add_note(entry.tcomment, note_type=NoteType.INSTRUCTION, author="translator")
            if entry.comment:
                for comment_line in entry.comment.split('\n'):
                     unit.add_note(comment_line, note_type=NoteType.GENERAL, author="extractor")
            if entry.occurrences:
                references = ", ".join([f"{path}:{line}" for path, line in entry.occurrences])
                unit.add_note(f"Reference: {references}", note_type=NoteType.GENERAL, author="reference")

            # Plural forms
            if entry.msgid_plural:
                unit.attributes['source_plural'] = entry.msgid_plural
                unit.attributes['target_plurals'] = entry.msgstr_plural

            # Store original flags and other metadata
            unit.attributes['polib_flags'] = entry.flags
            unit.attributes['polib_previous_msgid'] = entry.previous_msgid
            
            unit.original_format = self.format_name
            units.append(unit)
            
        return units

    def save(self, units: List[TranslationUnit], file_path: Path, **options) -> None:
        """
        Save translation units to a .po or .pot file.
        """
        po_file = polib.POFile()
        
        # Preserve header from original file if possible, or create a default one
        po_file.header = options.get('header', 'Default header for MUTT')
        po_file.metadata = options.get('metadata', {
            'Project-Id-Version': '1.0',
            'Report-Msgid-Bugs-To': '',
            'POT-Creation-Date': '',
            'PO-Revision-Date': '',
            'Last-Translator': '',
            'Language-Team': '',
            'MIME-Version': '1.0',
            'Content-Type': 'text/plain; charset=utf-8',
            'Content-Transfer-Encoding': '8bit',
        })

        for unit in units:
            entry = polib.POEntry()
            entry.msgid = unit.source
            entry.msgstr = unit.target
            entry.msgctxt = unit.context

            # Restore comments and occurrences
            tcomments = []
            comments = []
            occurrences = []
            for note in unit.notes:
                if note.author == "translator":
                    tcomments.append(note.text)
                elif note.author == "extractor":
                    comments.append(note.text)
                elif note.author == "reference" and "Reference: " in note.text:
                    # This is a simplification; robust parsing would be more complex
                    parts = note.text.replace("Reference: ", "").split(', ')
                    for part in parts:
                        if ':' in part:
                            path, line = part.rsplit(':', 1)
                            occurrences.append((path, line))

            entry.tcomment = "\n".join(tcomments)
            entry.comment = "\n".join(comments)
            if occurrences:
                entry.occurrences = occurrences

            # Restore plural forms
            if 'source_plural' in unit.attributes:
                entry.msgid_plural = unit.attributes['source_plural']
            if 'target_plurals' in unit.attributes:
                entry.msgstr_plural = unit.attributes['target_plurals']

            # Restore flags
            if unit.fuzzy:
                if 'fuzzy' not in entry.flags:
                    entry.flags.append('fuzzy')
            elif 'polib_flags' in unit.attributes:
                 entry.flags = unit.attributes['polib_flags']


            po_file.append(entry)

        try:
            po_file.save(str(file_path))
        except Exception as e:
            raise FormatHandlerError(f"Failed to save PO file: {e}") from e

    def validate(self, units: List[TranslationUnit]) -> ValidationResult:
        """
        Validate a list of TranslationUnits for suitability with the PO format.
        """
        result = ValidationResult(is_valid=True)
        for i, unit in enumerate(units):
            if not unit.source:
                result.add_error(f"Unit {i} has an empty source (msgid), which is invalid.")
            
            # Check for plural consistency
            has_source_plural = 'source_plural' in unit.attributes and unit.attributes['source_plural']
            has_target_plurals = 'target_plurals' in unit.attributes and isinstance(unit.attributes['target_plurals'], dict)

            if has_source_plural and not has_target_plurals:
                result.add_warning(f"Unit {i} has a source plural but no target plural forms.")
            if not has_source_plural and has_target_plurals:
                result.add_warning(f"Unit {i} has target plural forms but no source plural.")

        # A simple way to validate is to try saving to a dummy file in memory
        # but for now, the checks above are sufficient.
        return result