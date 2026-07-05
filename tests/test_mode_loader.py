"""Tests for mutt.logic.mode_loader — critical import target used
by app.py when instantiating Python-based chat modes."""
from __future__ import annotations

from mutt.logic import mode_loader


def test_instantiate_mode_is_exported():
    """Regression: app.py:779 relies on this symbol being importable.
    Missing it caused a NameError during the audit."""
    assert hasattr(mode_loader, "instantiate_mode")
    assert callable(mode_loader.instantiate_mode)


def test_discover_python_modes_is_exported():
    assert hasattr(mode_loader, "discover_python_modes")
    assert callable(mode_loader.discover_python_modes)
