"""Tests for the XLSX format handler."""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment

from format_handlers.base.translation_unit import TranslationUnit
from format_handlers.office.xlsx_handler import XlsxHandler


@pytest.fixture
def sample_xlsx(tmp_path: Path) -> Path:
    wb = Workbook()
    ws = wb.active
    ws.title = "Strings"
    ws["A1"] = "Title"
    ws["A2"] = "Subtitle"
    ws["B1"] = 42  # numeric, should be skipped
    ws["B2"] = "=A1"  # formula, should be skipped
    ws["C1"] = "With comment"
    ws["C1"].comment = Comment("Translator note", "qa")

    ws2 = wb.create_sheet("Second")
    ws2["A1"] = "Other sheet text"

    path = tmp_path / "sample.xlsx"
    wb.save(str(path))
    return path


def test_can_handle_xlsx_extension(sample_xlsx: Path):
    handler = XlsxHandler()
    assert handler.can_handle(sample_xlsx)


def test_can_handle_rejects_non_xlsx(tmp_path: Path):
    handler = XlsxHandler()
    assert not handler.can_handle(tmp_path / "foo.csv")


def test_load_skips_numeric_and_formula_cells(sample_xlsx: Path):
    handler = XlsxHandler()
    units = handler.load(sample_xlsx)
    sources = [u.source for u in units]
    assert "Title" in sources
    assert "Subtitle" in sources
    assert "With comment" in sources
    assert "Other sheet text" in sources
    assert 42 not in sources
    assert "=A1" not in sources


def test_load_unit_ids_use_sheet_coord_format(sample_xlsx: Path):
    handler = XlsxHandler()
    units = handler.load(sample_xlsx)
    for unit in units:
        assert "!" in unit.id
        sheet, coord = unit.id.split("!", 1)
        assert sheet in {"Strings", "Second"}
        assert coord[0].isalpha() and coord[1:].isdigit()


def test_load_captures_cell_comments(sample_xlsx: Path):
    handler = XlsxHandler()
    units = handler.load(sample_xlsx)
    comment_unit = next(u for u in units if u.source == "With comment")
    assert any("Translator note" in n.text for n in comment_unit.notes)


def test_save_round_trip_preserves_formulas(sample_xlsx: Path, tmp_path: Path):
    handler = XlsxHandler()
    units = handler.load(sample_xlsx)

    for unit in units:
        unit.target = unit.source.upper()

    out_path = tmp_path / "out.xlsx"
    handler.save(units, out_path, source_path=sample_xlsx)

    reloaded = load_workbook(str(out_path))
    assert reloaded["Strings"]["A1"].value == "TITLE"
    assert reloaded["Strings"]["A2"].value == "SUBTITLE"
    # Formula in B2 preserved.
    assert reloaded["Strings"]["B2"].value == "=A1"
    # Numeric cell preserved.
    assert reloaded["Strings"]["B1"].value == 42


def test_save_without_source_path(tmp_path: Path):
    handler = XlsxHandler()
    units = [
        TranslationUnit(id="Sheet1!A1", source="Hello"),
        TranslationUnit(id="Sheet1!A2", source="World"),
    ]
    for u in units:
        u.attributes["xlsx_sheet"] = "Sheet1"
        u.attributes["xlsx_coordinate"] = u.id.split("!")[1]
        u.target = u.source + "!"

    out_path = tmp_path / "new.xlsx"
    handler.save(units, out_path)

    wb = load_workbook(str(out_path))
    assert wb["Sheet1"]["A1"].value == "Hello!"
    assert wb["Sheet1"]["A2"].value == "World!"


def test_validate_flags_bad_unit_id():
    handler = XlsxHandler()
    units = [TranslationUnit(id="no-bang", source="x")]
    result = handler.validate(units)
    assert result.warnings, "Expected warning for id without '!'"


def test_format_capabilities_flags():
    caps = XlsxHandler().format_capabilities
    assert caps.binary_format is True
    assert caps.supports_comments is True


def test_load_releases_file_handle(sample_xlsx: Path, tmp_path: Path):
    """After load() returns, the source workbook must not be kept open so
    that the file can be renamed/overwritten on Windows."""
    handler = XlsxHandler()
    _ = handler.load(sample_xlsx)
    # Try to move the file — Windows will raise PermissionError if a handle
    # is still held.
    moved = tmp_path / "moved.xlsx"
    sample_xlsx.rename(moved)
    assert moved.exists()


def test_load_refuses_non_xlsx_bytes(tmp_path: Path):
    """Feeding a random .xlsx-named file should surface a FormatHandlerError."""
    from format_handlers.base.format_handler import FormatHandlerError

    bogus = tmp_path / "bogus.xlsx"
    bogus.write_bytes(b"not a real xlsx")
    handler = XlsxHandler()
    with pytest.raises(FormatHandlerError):
        handler.load(bogus)
