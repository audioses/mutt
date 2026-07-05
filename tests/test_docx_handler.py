"""Tests for the DOCX format handler."""

from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document

from format_handlers.base.translation_unit import TranslationUnit
from format_handlers.office.docx_handler import DocxHandler


@pytest.fixture
def sample_docx(tmp_path: Path) -> Path:
    doc = Document()
    doc.add_paragraph("Hello, world.")
    doc.add_paragraph("This is a second paragraph.")
    doc.add_paragraph("")  # empty — should be skipped
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Cell one"
    table.cell(0, 1).text = "Cell two"
    path = tmp_path / "sample.docx"
    doc.save(str(path))
    return path


def test_can_handle_docx_extension(sample_docx: Path):
    handler = DocxHandler()
    assert handler.can_handle(sample_docx)


def test_can_handle_rejects_non_docx(tmp_path: Path):
    handler = DocxHandler()
    assert not handler.can_handle(tmp_path / "foo.txt")


def test_load_extracts_paragraphs_and_table_cells(sample_docx: Path):
    handler = DocxHandler()
    units = handler.load(sample_docx)
    sources = [u.source for u in units]
    assert "Hello, world." in sources
    assert "This is a second paragraph." in sources
    assert "Cell one" in sources
    assert "Cell two" in sources
    # Empty paragraph is skipped.
    assert "" not in sources


def test_load_unit_ids_are_stable_addresses(sample_docx: Path):
    handler = DocxHandler()
    units = handler.load(sample_docx)
    for unit in units:
        assert unit.id.startswith(("p", "t")), unit.id
        assert unit.attributes["docx_address"] == unit.id


def test_save_round_trip_preserves_targets(sample_docx: Path, tmp_path: Path):
    handler = DocxHandler()
    units = handler.load(sample_docx)

    # Translate each unit by reversing its source.
    for unit in units:
        unit.target = unit.source[::-1]

    out_path = tmp_path / "out.docx"
    handler.save(units, out_path, source_path=sample_docx)

    assert out_path.exists()
    # Reload the saved document and confirm reversed text is present.
    reloaded = handler.load(out_path)
    reloaded_sources = {u.source for u in reloaded}
    for unit in units:
        assert unit.target in reloaded_sources


def test_save_without_source_path_writes_flat_paragraphs(tmp_path: Path):
    handler = DocxHandler()
    units = [
        TranslationUnit(id="p0", source="First"),
        TranslationUnit(id="p1", source="Second"),
    ]
    for u in units:
        u.target = u.source + "!"
    out_path = tmp_path / "flat.docx"
    handler.save(units, out_path)
    assert out_path.exists()
    doc = Document(str(out_path))
    texts = [p.text for p in doc.paragraphs]
    assert "First!" in texts
    assert "Second!" in texts


def test_format_capabilities_flags():
    caps = DocxHandler().format_capabilities
    assert caps.binary_format is True
    assert caps.preserves_structure is True
    assert caps.supports_inline_elements is True


def test_file_extensions_and_mime_types():
    handler = DocxHandler()
    assert ".docx" in handler.file_extensions
    assert ".dotx" in handler.file_extensions
    assert any("wordprocessingml.document" in m for m in handler.mime_types)
