"""Tests for the PPTX format handler."""

from __future__ import annotations

from pathlib import Path

import pytest
from pptx import Presentation
from pptx.util import Inches

from format_handlers.office.pptx_handler import PptxHandler


@pytest.fixture
def sample_pptx(tmp_path: Path) -> Path:
    prs = Presentation()
    blank_layout = prs.slide_layouts[5]  # Title Only.

    slide1 = prs.slides.add_slide(blank_layout)
    slide1.shapes.title.text = "First slide title"

    text_box = slide1.shapes.add_textbox(
        Inches(1), Inches(2), Inches(4), Inches(1)
    )
    tf = text_box.text_frame
    tf.text = "Body paragraph one"
    tf.add_paragraph().text = "Body paragraph two"

    slide2 = prs.slides.add_slide(blank_layout)
    slide2.shapes.title.text = "Second slide title"
    table_shape = slide2.shapes.add_table(
        rows=2, cols=2, left=Inches(1), top=Inches(2), width=Inches(5), height=Inches(2)
    ).table
    table_shape.cell(0, 0).text = "Header A"
    table_shape.cell(0, 1).text = "Header B"
    table_shape.cell(1, 0).text = "Cell A1"
    table_shape.cell(1, 1).text = "Cell B1"

    path = tmp_path / "sample.pptx"
    prs.save(str(path))
    return path


def test_can_handle_pptx(sample_pptx: Path):
    handler = PptxHandler()
    assert handler.can_handle(sample_pptx)


def test_can_handle_rejects_non_pptx(tmp_path: Path):
    handler = PptxHandler()
    assert not handler.can_handle(tmp_path / "foo.pdf")


def test_load_extracts_slide_text_and_tables(sample_pptx: Path):
    handler = PptxHandler()
    units = handler.load(sample_pptx)
    sources = [u.source for u in units]
    assert "First slide title" in sources
    assert "Body paragraph one" in sources
    assert "Body paragraph two" in sources
    assert "Second slide title" in sources
    assert "Header A" in sources
    assert "Cell B1" in sources


def test_load_unit_ids_encode_slide_path(sample_pptx: Path):
    handler = PptxHandler()
    units = handler.load(sample_pptx)
    # Unit ids start with s0. / s1.
    prefixes = {u.id.split(".")[0] for u in units}
    assert "s0" in prefixes
    assert "s1" in prefixes
    # Table unit ids contain .tbl.
    assert any(".tbl." in u.id for u in units)


def test_save_round_trip_preserves_text(sample_pptx: Path, tmp_path: Path):
    handler = PptxHandler()
    units = handler.load(sample_pptx)
    for unit in units:
        unit.target = unit.source.upper()

    out_path = tmp_path / "out.pptx"
    handler.save(units, out_path, source_path=sample_pptx)
    assert out_path.exists()

    reloaded = handler.load(out_path)
    sources = [u.source for u in reloaded]
    assert "FIRST SLIDE TITLE" in sources
    assert "BODY PARAGRAPH ONE" in sources
    assert "HEADER A" in sources
    assert "CELL B1" in sources


def test_save_without_source_path(tmp_path: Path):
    handler = PptxHandler()
    # Without a source presentation, save must still succeed (empty deck out).
    out_path = tmp_path / "empty.pptx"
    handler.save([], out_path)
    assert out_path.exists()


def test_format_capabilities_flags():
    caps = PptxHandler().format_capabilities
    assert caps.binary_format is True
    assert caps.preserves_structure is True
    assert caps.supports_inline_elements is True
