"""
MUTT Format Handler System

This package provides an extensible format handler architecture for MUTT,
supporting multiple translation file formats with rich metadata and workflow features.
"""

from .base.manager import FormatManager
from .base.translation_unit import TranslationUnit, TranslationStatus, Note, NoteType
from .base.format_handler import FormatHandler, FormatCapabilities, ValidationResult
from .base.registry import FormatRegistry, format_registry
from .base.detector import FormatDetector

__all__ = [
    'FormatManager',
    'TranslationUnit', 
    'TranslationStatus',
    'Note',
    'NoteType',
    'FormatHandler',
    'FormatCapabilities',
    'ValidationResult',
    'FormatRegistry',
    'format_registry',
    'FormatDetector'
]

__version__ = "1.0.0"