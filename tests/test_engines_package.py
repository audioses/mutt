"""Tests for mutt.engines package exports."""
from __future__ import annotations

import mutt.engines as engines


def test_engines_package_exports_argos_symbols():
    # These must be importable even if argostranslate isn't installed
    # (argos_engine module handles its own optional-dependency fallbacks).
    for name in (
        "ARGOS_AVAILABLE",
        "get_installed_languages",
        "update_package_index",
        "get_available_packages",
        "download_and_install_package",
        "install_from_path",
        "translate_text",
        "ArgosError",
        "ArgosPackageMissingError",
    ):
        assert hasattr(engines, name), f"engines package missing {name}"


def test_engines_package_exports_hf_symbols_even_when_optional():
    # HF optional — names must still be defined (set to None if unavailable)
    for name in ("HF_AVAILABLE", "HFModelManager", "HFTranslator", "HuggingFaceEngine"):
        assert hasattr(engines, name), f"engines package missing {name}"


def test_engines_all_is_complete():
    assert hasattr(engines, "__all__")
    required = {
        "ARGOS_AVAILABLE", "ArgosError", "ArgosPackageMissingError",
        "HF_AVAILABLE",
    }
    assert required.issubset(set(engines.__all__))
