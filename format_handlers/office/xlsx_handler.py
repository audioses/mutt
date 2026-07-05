"""Format handler for Microsoft Excel (.xlsx/.xlsm) files using openpyxl."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from openpyxl import Workbook, load_workbook

from ..base.format_handler import (
    FormatCapabilities,
    FormatHandler,
    FormatHandlerError,
    ValidationResult,
)
from ..base.translation_unit import (
    NoteType,
    TranslationStatus,
    TranslationUnit,
)
from ._zip_safety import OfficeZipBombError, assert_safe_office_zip


_ZIP_MAGIC = b"PK\x03\x04"


class XlsxHandler(FormatHandler):
    """Reads and writes ``.xlsx``/``.xlsm`` workbooks.

    Each non-empty *string* cell becomes a :class:`TranslationUnit`. Numeric
    cells, dates, and formulas are deliberately skipped — they are not
    translation content. The unit id is the familiar ``Sheet!A1`` coordinate,
    which makes the round-trip write trivial and human-readable.
    """

    @property
    def format_name(self) -> str:
        return "Microsoft Excel XLSX"

    @property
    def file_extensions(self) -> List[str]:
        return [".xlsx", ".xlsm"]

    @property
    def mime_types(self) -> List[str]:
        return [
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel.sheet.macroEnabled.12",
        ]

    @property
    def format_capabilities(self) -> FormatCapabilities:
        caps = FormatCapabilities()
        caps.binary_format = True
        caps.preserves_structure = True
        caps.supports_comments = True
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
        keep_vba = file_path.suffix.lower() == ".xlsm"
        try:
            assert_safe_office_zip(file_path)
            workbook = load_workbook(
                filename=str(file_path),
                data_only=False,
                keep_vba=keep_vba,
            )
        except OfficeZipBombError as exc:
            raise FormatHandlerError(f"Refused to parse XLSX: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            raise FormatHandlerError(f"Failed to parse XLSX: {exc}") from exc

        units: List[TranslationUnit] = []
        try:
            for sheet in workbook.worksheets:
                for row in sheet.iter_rows():
                    for cell in row:
                        unit = self._cell_to_unit(sheet.title, cell)
                        if unit is not None:
                            units.append(unit)
        finally:
            # Release the underlying file handle so the source file is not
            # left locked on Windows.
            try:
                workbook.close()
            except Exception:  # noqa: BLE001
                pass
        return units

    @staticmethod
    def _cell_to_unit(sheet_title: str, cell) -> Optional[TranslationUnit]:
        value = cell.value
        if not isinstance(value, str):
            return None
        text = value.strip()
        if not text:
            return None
        # Skip formulas (values starting with '=').
        if text.startswith("="):
            return None
        unit_id = f"{sheet_title}!{cell.coordinate}"
        unit = TranslationUnit(id=unit_id, source=value)
        unit.target = ""
        unit.status = TranslationStatus.NEW
        unit.original_format = "Microsoft Excel XLSX"
        unit.attributes["xlsx_sheet"] = sheet_title
        unit.attributes["xlsx_coordinate"] = cell.coordinate
        if cell.comment and cell.comment.text:
            unit.add_note(cell.comment.text, author="excel", note_type=NoteType.GENERAL)
        return unit

    # -------------------------------------------------------------------- save
    def save(
        self,
        units: List[TranslationUnit],
        file_path: Path,
        **options,
    ) -> None:
        source_path = options.get("source_path")
        workbook: Optional[Workbook] = None
        try:
            if source_path is not None and Path(source_path).exists():
                assert_safe_office_zip(Path(source_path))
                keep_vba = Path(source_path).suffix.lower() == ".xlsm"
                workbook = load_workbook(
                    filename=str(source_path),
                    data_only=False,
                    keep_vba=keep_vba,
                )
            else:
                workbook = Workbook()
                # Remove default empty sheet so we only have what we write.
                default_sheet = workbook.active
                workbook.remove(default_sheet)

            sheets_cache: Dict[str, Any] = {ws.title: ws for ws in workbook.worksheets}

            for unit in units:
                sheet_title = unit.attributes.get("xlsx_sheet")
                coord = unit.attributes.get("xlsx_coordinate")
                if not sheet_title or not coord:
                    # Try to parse id.
                    if "!" in unit.id:
                        sheet_title, coord = unit.id.split("!", 1)
                    else:
                        continue

                worksheet = sheets_cache.get(sheet_title)
                if worksheet is None:
                    worksheet = workbook.create_sheet(sheet_title)
                    sheets_cache[sheet_title] = worksheet
                worksheet[coord] = unit.target or unit.source

            workbook.save(str(file_path))
        except OfficeZipBombError as exc:
            raise FormatHandlerError(f"Refused to save XLSX: {exc}") from exc
        except FormatHandlerError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise FormatHandlerError(f"Failed to save XLSX: {exc}") from exc
        finally:
            if workbook is not None:
                try:
                    workbook.close()
                except Exception:  # noqa: BLE001
                    pass

    # ---------------------------------------------------------------- validate
    def validate(self, units: List[TranslationUnit]) -> ValidationResult:
        result = ValidationResult(is_valid=True)
        for i, unit in enumerate(units):
            if not unit.source:
                result.add_warning(f"Unit {i} has empty source")
            if "!" not in (unit.id or ""):
                result.add_warning(
                    f"Unit {i} id '{unit.id}' is not a Sheet!Coord address"
                )
        return result

    def get_metadata(self, file_path: Path) -> Dict[str, Any]:
        meta = super().get_metadata(file_path)
        try:
            wb = load_workbook(str(file_path), read_only=True, data_only=False)
            meta.update(
                {
                    "sheet_count": len(wb.sheetnames),
                    "sheet_names": list(wb.sheetnames),
                }
            )
            wb.close()
        except Exception:  # noqa: BLE001
            pass
        return meta
