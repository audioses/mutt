"""
Base classes and core components for the format handler system.
"""

from .translation_unit import TranslationUnit, TranslationStatus, Note, NoteType
from .format_handler import FormatHandler, FormatCapabilities, ValidationResult
from .registry import FormatRegistry, format_registry
from .detector import FormatDetector
from .manager import FormatManager

__all__ = [
    'TranslationUnit',
    'TranslationStatus', 
    'Note',
    'NoteType',
    'FormatHandler',
    'FormatCapabilities',
    'ValidationResult',
    'FormatRegistry',
    'format_registry',
    'FormatDetector',
    'FormatManager'
]