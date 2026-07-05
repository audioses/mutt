"""Regression guard: local_model_manager must import without NameError.

The audit found `re` used without being imported, causing runtime NameError
inside the bytes-sanitization paths. This test ensures the module is
importable and the `re` symbol is actually bound inside it.
"""
from __future__ import annotations

import importlib
import local_model_manager


def test_module_imports_cleanly():
    importlib.reload(local_model_manager)


def test_re_is_available_in_module_namespace():
    """Regression for lines 312/324/405/414 where `re.match/re.sub` crashed."""
    assert hasattr(local_model_manager, "re")
