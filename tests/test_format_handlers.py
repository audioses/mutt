"""Tests for format_handlers auto-discovery and registry."""
from __future__ import annotations

from pathlib import Path

from format_handlers.base.manager import FormatManager


def test_format_manager_constructs_without_error():
    """Smoke test: construction must not raise on a clean checkout."""
    FormatManager()


def test_format_manager_discovers_expected_handlers():
    mgr = FormatManager()
    fmts = mgr.get_supported_formats()
    assert isinstance(fmts, dict)
    # Names are human-readable strings like "JSON", "HTML"
    names_lower = {name.lower() for name in fmts.keys()}
    for expected in ("json", "html", "xliff", "docx", "xlsx", "pptx"):
        assert any(expected in n for n in names_lower), (
            f"{expected!r} handler not registered; got {list(fmts.keys())}"
        )


def test_format_manager_provides_wildcard_for_dialogs():
    mgr = FormatManager()
    wc = mgr.get_file_dialog_wildcard()
    assert isinstance(wc, str) and len(wc) > 0


def test_format_manager_can_detect_known_extensions(tmp_path):
    mgr = FormatManager()
    json_file = tmp_path / "x.json"
    json_file.write_text('{"a":"b"}', encoding="utf-8")
    # detect_file_format expects a Path-like object (not str)
    fmt = mgr.detect_file_format(Path(json_file))
    assert fmt is not None
