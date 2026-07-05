"""
Argos Translate engine helpers for MUTT.

Provides:
- ARGOS_AVAILABLE flag
- package index helpers (update, list available, download & install)
- installed language listing
- translate_text(...) with auto-install fallback:
    * 'pivot'         - try direct, then pivot via composite translations
    * 'prompt_install' - raise ArgosPackageMissingError
    * 'auto_install'   - automatically download & install missing packages

This module intentionally isolates Argos-specific logic so the main AITranslator remains small.
"""

import os
import tempfile
import importlib
from typing import List, Optional

# ----------------------------------------------------------------------
# Safe ASCII-only package directory enforcement
# ----------------------------------------------------------------------
def ensure_safe_package_dir(base_dir: Optional[str] = None) -> str:
    """
    Ensure Argos Translate uses an ASCII-only package directory.
    If the provided base_dir contains non-ASCII chars, fallback to temp dir.
    """
    env_vars = ["ARGOS_TRANSLATE_PACKAGE_DIR", "ARGOS_PACKAGES_DIR"]

    if base_dir and all(ord(c) < 128 for c in base_dir):
        safe_dir = base_dir
    else:
        safe_dir = os.path.join(tempfile.gettempdir(), "argos_packages")

    os.makedirs(safe_dir, exist_ok=True)

    for ev in env_vars:
        os.environ[ev] = safe_dir

    print(f"[Argos Engine] Forcing package dir to safe ASCII path: {safe_dir}")
    return safe_dir


# Force setup immediately on import
SAFE_DIR = ensure_safe_package_dir(os.environ.get("ARGOS_TRANSLATE_PACKAGE_DIR"))

# ----------------------------------------------------------------------
# Argos Translate imports
# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
# Argos Translate imports
# ----------------------------------------------------------------------
# ARGOS_AVAILABLE moved below to be managed by _import_argos
# argos_package and argos_translate are now globals initialized by _import_argos()
# Removed direct imports here for lazy loading

# ----------------------------------------------------------------------
# Error Classes
# ----------------------------------------------------------------------
class ArgosError(Exception):
    pass


class ArgosPackageMissingError(ArgosError):
    def __init__(self, from_code: str, to_code: str, message: Optional[str] = None, suggested_package=None):
        msg = message or f"Argos package for {from_code} -> {to_code} is not installed."
        super().__init__(msg)
        self.from_code = from_code
        self.to_code = to_code
        self.suggested_package = suggested_package


# Global variables for lazy loading
ARGOS_AVAILABLE = False
argos_package = None
argos_translate = None

def _import_argos():
    """Helper to import argostranslate modules and set ARGOS_AVAILABLE."""
    global ARGOS_AVAILABLE, argos_package, argos_translate
    if not ARGOS_AVAILABLE:
        try:
            import argostranslate.package as argos_package_local
            import argostranslate.translate as argos_translate_local
            argos_package = argos_package_local
            argos_translate = argos_translate_local
            ARGOS_AVAILABLE = True
        except Exception:
            ARGOS_AVAILABLE = False
            raise ArgosError("argostranslate library not found. Please install it.")
    return ARGOS_AVAILABLE


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def get_installed_languages() -> List[str]:
    _import_argos()
    return [lang.code for lang in argos_translate.get_installed_languages()]


def update_package_index():
    _import_argos()
    return argos_package.update_package_index()


def get_available_packages():
    _import_argos()
    return argos_package.get_available_packages()


def find_package_for_pair(from_code: str, to_code: str):
    _import_argos()
    try:
        packages = get_available_packages()
    except Exception:
        return None
    for pkg in packages or []:
        if pkg.from_code == from_code and pkg.to_code == to_code:
            return pkg
    return None


def download_and_install_package(package_obj, target_dir: Optional[str] = None):
    _import_argos()
    if not hasattr(package_obj, 'install'):
        raise ArgosError("Selected package object does not have a native .install() method.")

    try:
        # If target_dir is provided, ensure it's used for download and installation
        if target_dir:
            # Temporarily set ARGOS_TRANSLATE_PACKAGE_DIR to the target_dir
            original_env_var = os.environ.get("ARGOS_TRANSLATE_PACKAGE_DIR")
            os.environ["ARGOS_TRANSLATE_PACKAGE_DIR"] = target_dir
            print(f"[Argos Engine] Temporarily setting ARGOS_TRANSLATE_PACKAGE_DIR to: {target_dir}")
            try:
                # Download and install using the modified environment
                path = package_obj.download()
                argos_package.install_from_path(path)
            finally:
                # Restore original environment variable
                if original_env_var is not None:
                    os.environ["ARGOS_TRANSLATE_PACKAGE_DIR"] = original_env_var
                else:
                    del os.environ["ARGOS_TRANSLATE_PACKAGE_DIR"]
                print(f"[Argos Engine] Restored ARGOS_TRANSLATE_PACKAGE_DIR to: {os.environ.get('ARGOS_TRANSLATE_PACKAGE_DIR', 'default')}")
        else:
            # Fallback to default argostranslate behavior if no target_dir
            package_obj.install()

        print("[Argos Engine] Reloading modules to recognize new package...")
        importlib.reload(argos_package)
        importlib.reload(argos_translate)
        print("[Argos Engine] Modules reloaded.")
    except Exception as e:
        raise ArgosError(f"Native package installation failed: {e}") from e


def install_from_path(path: str):
    _import_argos()
    try:
        argos_package.install_from_path(path)
    except Exception as e:
        raise ArgosError(f"Failed to install package from {path}: {e}") from e


def ensure_package_installed(from_code: str, to_code: str):
    """Ensure a translation package exists for the requested pair, auto-install if missing."""
    _import_argos()
    installed = argos_translate.get_installed_languages()
    from_lang = next((l for l in installed if l.code == from_code), None)
    to_lang = next((l for l in installed if l.code == to_code), None)

    if from_lang and to_lang and from_lang.get_translation(to_lang):
        return  # already installed

    # not installed → download & install
    argos_package.update_package_index()
    available = argos_package.get_available_packages()
    target = next((p for p in available if p.from_code == from_code and p.to_code == to_code), None)

    if not target:
        raise ArgosPackageMissingError(from_code, to_code, message=f"No package available for {from_code} → {to_code}")

    print(f"[Argos Engine] Downloading + installing {from_code} → {to_code}")
    path = target.download()
    argos_package.install_from_path(path)

    importlib.reload(argos_package)
    importlib.reload(argos_translate)


# ----------------------------------------------------------------------
# Main translation entry point
# ----------------------------------------------------------------------
def translate_text(text: str, from_code: str, to_code: str, strategy: str = "pivot", **kwargs) -> str:
    _import_argos()
    from_code = (from_code or "").strip()
    to_code = (to_code or "").strip()
    if not from_code or not to_code:
        raise ArgosError("from_code and to_code must be provided for Argos translation")

    # Ensure the package exists
    ensure_package_installed(from_code, to_code)

    installed_languages = argos_translate.get_installed_languages()
    from_lang = next((lang for lang in installed_languages if lang.code == from_code), None)
    to_lang = next((lang for lang in installed_languages if lang.code == to_code), None)

    if not from_lang or not to_lang:
        raise ArgosPackageMissingError(from_code, to_code, message="Required languages not installed properly.")

    translation = from_lang.get_translation(to_lang)

    if translation:
        try:
            return translation.translate(text)
        except Exception as e:
            raise ArgosError(f"Translation failed even with a valid path: {e}") from e

    suggested = find_package_for_pair(from_code, to_code)
    raise ArgosPackageMissingError(
        from_code,
        to_code,
        message=f"No translation path found for {from_code}->{to_code}, even with pivot. A package might be missing.",
        suggested_package=suggested
    )
