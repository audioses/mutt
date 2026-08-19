"""Saving an XLIFF to a NEW path must reuse the source file's structure."""
from __future__ import annotations

from pathlib import Path

from format_handlers.localization.xliff_handler import XLIFFHandler

SAMPLE = """<?xml version="1.0" encoding="utf-8"?>
<xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">
  <file source-language="en" target-language="tr" datatype="plaintext" original="app">
    <body>
      <trans-unit id="1">
        <source>report usage</source>
        <target>kullanimi raporla</target>
      </trans-unit>
    </body>
  </file>
</xliff>
"""


def test_save_to_new_path_uses_source_structure(tmp_path: Path):
    src = tmp_path / "changes.xliff"
    src.write_text(SAMPLE, encoding="utf-8")
    handler = XLIFFHandler()
    units = handler.load(src)
    units[0].target = "kullanimi bildir"

    out = tmp_path / "changes_translated.xliff"  # does not exist yet
    handler.save(units, out, source_path=src)

    assert "kullanimi bildir" in out.read_text(encoding="utf-8")
    assert handler.load(out)[0].target == "kullanimi bildir"
