# Engine package exports
from .argos_engine import (
    ARGOS_AVAILABLE,
    get_installed_languages,
    update_package_index,
    get_available_packages,
    download_and_install_package,
    install_from_path,
    translate_text,
    ArgosError,
    ArgosPackageMissingError,
)

# Optional Hugging Face engine exports
try:
    from .hf_engine import HF_AVAILABLE, HFModelManager, HFTranslator, HuggingFaceEngine
except Exception:
    # hf_engine may be unavailable if dependencies are missing
    HF_AVAILABLE = False
    HFModelManager = None
    HFTranslator = None
    HuggingFaceEngine = None

__all__ = [
    "ARGOS_AVAILABLE",
    "get_installed_languages",
    "update_package_index",
    "get_available_packages",
    "download_and_install_package",
    "install_from_path",
    "translate_text",
    "ArgosError",
    "ArgosPackageMissingError",
    "HF_AVAILABLE",
    "HFModelManager",
    "HFTranslator",
    "HuggingFaceEngine",
]
