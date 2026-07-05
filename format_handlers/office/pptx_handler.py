"""Format handler for Microsoft PowerPoint (.pptx) files using python-pptx."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from pptx import Presentation

from ..base.format_handler import (
    FormatCapabilities,
    FormatHandler,
    FormatHandlerError,
    ValidationResult,
)
from ..base.translation_unit import TranslationStatus, TranslationUnit
from ._zip_safety import OfficeZipBombError, assert_safe_office_zip


_ZIP_MAGIC = b"PK\x03\x04"


class PptxHandler(FormatHandler):
    """Reads and writes ``.pptx``/``.potx`` presentations.

    Walks every slide → shape → text_frame → paragraph. Each paragraph with
    non-empty text becomes a :class:`TranslationUnit`. Shape-level tables are
    also walked cell-by-cell. The unit id encodes the path so the save pass
    can round-trip without a reverse-lookup table.
    """

    @property
    def format_name(self) -> str:
        return "Microsoft PowerPoint PPTX"

    @property
    def file_extensions(self) -> List[str]:
        return [".pptx", ".potx"]

    @property
    def mime_types(self) -> List[str]:
        return [
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "application/vnd.openxmlformats-officedocument.presentationml.template",
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
            return content_sample.startswith(_ZIP_MAGIC)
        return True

    # -------------------------------------------------------------------- load
    def load(self, file_path: Path, **options) -> List[TranslationUnit]:
        try:
            assert_safe_office_zip(file_path)
            presentation = Presentation(str(file_path))
        except OfficeZipBombError as exc:
            raise FormatHandlerError(f"Refused to parse PPTX: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            raise FormatHandlerError(f"Failed to parse PPTX: {exc}") from exc

        units: List[TranslationUnit] = []
        for s_idx, slide in enumerate(presentation.slides):
            for sh_idx, shape in enumerate(slide.shapes):
                units.extend(self._shape_to_units(s_idx, sh_idx, shape))
        return units

    def _shape_to_units(self, s_idx: int, sh_idx: int, shape) -> List[TranslationUnit]:
        units: List[TranslationUnit] = []
        if shape.has_text_frame:
            for p_idx, paragraph in enumerate(shape.text_frame.paragraphs):
                text = "".join(run.text for run in paragraph.runs) or paragraph.text
                unit = self._paragraph_unit(
                    unit_id=f"s{s_idx}.sh{sh_idx}.p{p_idx}", text=text
                )
                if unit is not None:
                    units.append(unit)
        if shape.has_table:
            table = shape.table
            for r_idx, row in enumerate(table.rows):
                for c_idx, cell in enumerate(row.cells):
                    if cell.text_frame is None:
                        continue
                    for p_idx, paragraph in enumerate(cell.text_frame.paragraphs):
                        text = "".join(run.text for run in paragraph.runs) or paragraph.text
                        unit_id = (
                            f"s{s_idx}.sh{sh_idx}.tbl.r{r_idx}.c{c_idx}.p{p_idx}"
                        )
                        unit = self._paragraph_unit(unit_id=unit_id, text=text)
                        if unit is not None:
                            units.append(unit)
        return units

    @staticmethod
    def _paragraph_unit(*, unit_id: str, text: str) -> Optional[TranslationUnit]:
        if not text or not text.strip():
            return None
        unit = TranslationUnit(id=unit_id, source=text)
        unit.target = ""
        unit.status = TranslationStatus.NEW
        unit.original_format = "Microsoft PowerPoint PPTX"
        unit.attributes["pptx_address"] = unit_id
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
                presentation = Presentation(str(source_path))
            else:
                presentation = Presentation()

            by_address: Dict[str, TranslationUnit] = {
                unit.attributes.get("pptx_address", unit.id): unit for unit in units
            }

            for s_idx, slide in enumerate(presentation.slides):
                for sh_idx, shape in enumerate(slide.shapes):
                    self._apply_units_to_shape(s_idx, sh_idx, shape, by_address)

            presentation.save(str(file_path))
        except FormatHandlerError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise FormatHandlerError(f"Failed to save PPTX: {exc}") from exc

    def _apply_units_to_shape(
        self,
        s_idx: int,
        sh_idx: int,
        shape,
        by_address: Dict[str, TranslationUnit],
    ) -> None:
        if shape.has_text_frame:
            for p_idx, paragraph in enumerate(shape.text_frame.paragraphs):
                unit = by_address.get(f"s{s_idx}.sh{sh_idx}.p{p_idx}")
                if unit is not None:
                    self._replace_paragraph_text(paragraph, unit.target or unit.source)
        if shape.has_table:
            for r_idx, row in enumerate(shape.table.rows):
                for c_idx, cell in enumerate(row.cells):
                    if cell.text_frame is None:
                        continue
                    for p_idx, paragraph in enumerate(cell.text_frame.paragraphs):
                        key = f"s{s_idx}.sh{sh_idx}.tbl.r{r_idx}.c{c_idx}.p{p_idx}"
                        unit = by_address.get(key)
                        if unit is not None:
                            self._replace_paragraph_text(
                                paragraph, unit.target or unit.source
                            )

    @staticmethod
    def _replace_paragraph_text(paragraph, new_text: str) -> None:
        runs = list(paragraph.runs)
        if not runs:
            # python-pptx paragraph has no add_run that preserves style; fall
            # back to setting the full paragraph text.
            paragraph.text = new_text
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
            prs = Presentation(str(file_path))
            meta["slide_count"] = len(prs.slides)
        except Exception:  # noqa: BLE001
            pass
        return meta
