"""Format handler for Microsoft Word (.docx) files using python-docx."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from docx import Document

from ..base.format_handler import (
    FormatCapabilities,
    FormatHandler,
    FormatHandlerError,
    ValidationResult,
)
from ..base.translation_unit import TranslationStatus, TranslationUnit
from ._zip_safety import OfficeZipBombError, assert_safe_office_zip


_ZIP_MAGIC = b"PK\x03\x04"


class DocxHandler(FormatHandler):
    """Reads and writes ``.docx``/``.dotx`` files.

    Each paragraph (including paragraphs inside table cells) is mapped to a
    single :class:`TranslationUnit`. The unit's ``attributes`` dictionary
    stores a stable address so :meth:`save` can rewrite the source document
    in place, preserving images, styles, headers, and everything else the
    handler does not explicitly touch.
    """

    @property
    def format_name(self) -> str:
        return "Microsoft Word DOCX"

    @property
    def file_extensions(self) -> List[str]:
        return [".docx", ".dotx"]

    @property
    def mime_types(self) -> List[str]:
        return [
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.template",
        ]

    @property
    def format_capabilities(self) -> FormatCapabilities:
        caps = FormatCapabilities()
        caps.binary_format = True
        caps.preserves_structure = True
        caps.supports_inline_elements = True
        caps.supports_attributes = True
        caps.supports_file_metadata = True
        return caps

    # ------------------------------------------------------------------ detect
    def can_handle(self, file_path: Path, content_sample: bytes = None) -> bool:
        if file_path.suffix.lower() not in self.file_extensions:
            return False
        if content_sample is not None:
            # .docx is a ZIP container; reject obvious non-ZIP content.
            return content_sample.startswith(_ZIP_MAGIC)
        return True

    # -------------------------------------------------------------------- load
    def load(self, file_path: Path, **options) -> List[TranslationUnit]:
        try:
            assert_safe_office_zip(file_path)
            document = Document(str(file_path))
        except OfficeZipBombError as exc:
            raise FormatHandlerError(f"Refused to parse DOCX: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 - wrap any parser error
            raise FormatHandlerError(f"Failed to parse DOCX: {exc}") from exc

        units: List[TranslationUnit] = []

        # Top-level paragraphs.
        for p_idx, paragraph in enumerate(document.paragraphs):
            unit = self._paragraph_to_unit(paragraph, unit_id=f"p{p_idx}")
            if unit is not None:
                units.append(unit)

        # Paragraphs inside tables.
        for t_idx, table in enumerate(document.tables):
            for r_idx, row in enumerate(table.rows):
                for c_idx, cell in enumerate(row.cells):
                    for p_idx, paragraph in enumerate(cell.paragraphs):
                        unit_id = f"t{t_idx}.r{r_idx}.c{c_idx}.p{p_idx}"
                        unit = self._paragraph_to_unit(paragraph, unit_id=unit_id)
                        if unit is not None:
                            units.append(unit)

        return units

    def _paragraph_to_unit(self, paragraph, *, unit_id: str) -> Optional[TranslationUnit]:
        text = paragraph.text
        if not text.strip():
            return None
        unit = TranslationUnit(id=unit_id, source=text)
        unit.target = ""
        unit.status = TranslationStatus.NEW
        unit.original_format = self.format_name
        unit.attributes["docx_address"] = unit_id
        unit.attributes["docx_style"] = paragraph.style.name if paragraph.style else None
        return unit

    # -------------------------------------------------------------------- save
    def save(
        self,
        units: List[TranslationUnit],
        file_path: Path,
        **options,
    ) -> None:
        source_path = options.get("source_path")
        try:
            if source_path is not None and Path(source_path).exists():
                document = Document(str(source_path))
            else:
                document = Document()
                # No source document — render each unit as its own paragraph.
                for unit in units:
                    document.add_paragraph(unit.target or unit.source)
                document.save(str(file_path))
                return

            by_address: Dict[str, TranslationUnit] = {
                unit.attributes.get("docx_address", unit.id): unit for unit in units
            }

            # Replace paragraphs.
            for p_idx, paragraph in enumerate(document.paragraphs):
                unit = by_address.get(f"p{p_idx}")
                if unit is not None:
                    self._replace_paragraph_text(paragraph, unit.target or unit.source)

            # Replace paragraphs inside table cells.
            for t_idx, table in enumerate(document.tables):
                for r_idx, row in enumerate(table.rows):
                    for c_idx, cell in enumerate(row.cells):
                        for p_idx, paragraph in enumerate(cell.paragraphs):
                            key = f"t{t_idx}.r{r_idx}.c{c_idx}.p{p_idx}"
                            unit = by_address.get(key)
                            if unit is not None:
                                self._replace_paragraph_text(
                                    paragraph, unit.target or unit.source
                                )

            document.save(str(file_path))
        except FormatHandlerError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise FormatHandlerError(f"Failed to save DOCX: {exc}") from exc

    @staticmethod
    def _replace_paragraph_text(paragraph, new_text: str) -> None:
        """Replace the paragraph's text while keeping the first run's formatting."""
        runs = list(paragraph.runs)
        if not runs:
            paragraph.add_run(new_text)
            return
        runs[0].text = new_text
        for extra in runs[1:]:
            extra.text = ""

    # ---------------------------------------------------------------- validate
    def validate(self, units: List[TranslationUnit]) -> ValidationResult:
        result = ValidationResult(is_valid=True)
        for i, unit in enumerate(units):
            if not unit.source:
                result.add_warning(f"Unit {i} has empty source")
        return result

    def get_metadata(self, file_path: Path) -> Dict[str, Any]:
        meta = super().get_metadata(file_path)
        try:
            doc = Document(str(file_path))
            core = doc.core_properties
            meta.update(
                {
                    "title": core.title or "",
                    "author": core.author or "",
                    "paragraph_count": len(doc.paragraphs),
                    "table_count": len(doc.tables),
                }
            )
        except Exception:  # noqa: BLE001
            pass
        return meta
