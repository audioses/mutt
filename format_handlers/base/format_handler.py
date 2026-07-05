"""
Abstract base class and supporting classes for format handlers.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, BinaryIO, TextIO
from pathlib import Path
from .translation_unit import TranslationUnit


class FormatCapabilities:
    """Defines what features a format supports."""
    
    def __init__(self, **kwargs):
        self.supports_comments: bool = False
        self.supports_context: bool = False
        self.supports_plural_forms: bool = False
        self.supports_fuzzy_matching: bool = False
        self.supports_translation_status: bool = False
        self.supports_review_workflow: bool = False
        self.supports_character_limits: bool = False
        self.supports_placeholders: bool = False
        self.supports_file_metadata: bool = False
        self.supports_inline_elements: bool = False
        self.supports_attributes: bool = False
        self.binary_format: bool = False
        self.preserves_structure: bool = True
        
        # Set attributes based on kwargs
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
            else:
                raise TypeError(f"FormatCapabilities.__init__() got an unexpected keyword argument '{key}'")
    
    def to_dict(self) -> Dict[str, bool]:
        """Convert capabilities to dictionary."""
        return {
            'comments': self.supports_comments,
            'context': self.supports_context,
            'plural_forms': self.supports_plural_forms,
            'fuzzy_matching': self.supports_fuzzy_matching,
            'translation_status': self.supports_translation_status,
            'review_workflow': self.supports_review_workflow,
            'character_limits': self.supports_character_limits,
            'placeholders': self.supports_placeholders,
            'file_metadata': self.supports_file_metadata,
            'inline_elements': self.supports_inline_elements,
            'attributes': self.supports_attributes,
            'binary_format': self.binary_format,
            'structure_preservation': self.preserves_structure
        }


class ValidationResult:
    """Result of format validation."""
    
    def __init__(self, is_valid: bool, errors: List[str] = None, warnings: List[str] = None):
        self.is_valid = is_valid
        self.errors = errors or []
        self.warnings = warnings or []
    
    def add_error(self, error: str) -> None:
        """Add an error to the validation result."""
        self.errors.append(error)
        self.is_valid = False
    
    def add_warning(self, warning: str) -> None:
        """Add a warning to the validation result."""
        self.warnings.append(warning)
    
    def has_issues(self) -> bool:
        """Check if there are any errors or warnings."""
        return bool(self.errors or self.warnings)
    
    def __str__(self):
        if self.is_valid and not self.warnings:
            return "Valid"
        
        parts = []
        if not self.is_valid:
            parts.append(f"INVALID: {len(self.errors)} errors")
        if self.warnings:
            parts.append(f"{len(self.warnings)} warnings")
        
        return ", ".join(parts)


class FormatHandlerError(Exception):
    """Base exception for format handler errors."""
    pass


class ValidationError(FormatHandlerError):
    """Exception raised when validation fails."""
    pass


class FormatHandler(ABC):
    """
    Abstract base class for all format handlers.
    
    This class defines the interface that all format handlers must implement
    to work with the MUTT format system. It provides methods for
    loading, saving, validating, and detecting translation files.
    """
    
    @property
    @abstractmethod
    def format_name(self) -> str:
        """Human-readable format name (e.g., 'GNU Gettext PO')."""
        pass
    
    @property
    @abstractmethod
    def file_extensions(self) -> List[str]:
        """Supported file extensions (e.g., ['.po', '.pot'])."""
        pass
    
    @property
    @abstractmethod
    def mime_types(self) -> List[str]:
        """Supported MIME types (e.g., ['text/x-gettext-translation'])."""
        pass
    
    @property
    @abstractmethod
    def format_capabilities(self) -> FormatCapabilities:
        """What features this format supports."""
        pass
    
    # Core methods that must be implemented
    @abstractmethod
    def can_handle(self, file_path: Path, content_sample: bytes = None) -> bool:
        """
        Determine if this handler can process the given file.
        
        Args:
            file_path: Path to the file to check
            content_sample: Optional sample of file content (first 8KB)
        
        Returns:
            True if this handler can process the file
        """
        pass
    
    @abstractmethod
    def load(self, file_path: Path, **options) -> List[TranslationUnit]:
        """
        Load translation units from file.
        
        Args:
            file_path: Path to the file to load
            **options: Format-specific loading options
        
        Returns:
            List of TranslationUnit objects
        
        Raises:
            FormatHandlerError: If loading fails
        """
        pass
    
    @abstractmethod
    def save(self, units: List[TranslationUnit], file_path: Path, **options) -> None:
        """
        Save translation units to file.
        
        Args:
            units: List of TranslationUnit objects to save
            file_path: Path where to save the file
            **options: Format-specific saving options
        
        Raises:
            FormatHandlerError: If saving fails
        """
        pass
    
    # Optional methods with default implementations
    def validate(self, units: List[TranslationUnit]) -> ValidationResult:
        """
        Validate translation units for this format.
        
        Args:
            units: List of TranslationUnit objects to validate
        
        Returns:
            ValidationResult indicating if units are valid
        """
        result = ValidationResult(is_valid=True)
        
        # Basic validation - check for empty source texts
        for i, unit in enumerate(units):
            if unit.is_empty():
                result.add_warning(f"Unit {i} has empty source text")
        
        return result
    
    def get_metadata(self, file_path: Path) -> Dict[str, Any]:
        """
        Extract file-level metadata.
        
        Args:
            file_path: Path to the file
        
        Returns:
            Dictionary of metadata
        """
        return {
            'file_size': file_path.stat().st_size if file_path.exists() else 0,
            'file_name': file_path.name,
            'format_name': self.format_name
        }
    
    def supports_feature(self, feature: str) -> bool:
        """
        Check if handler supports specific feature.
        
        Args:
            feature: Feature name to check
        
        Returns:
            True if feature is supported
        """
        return hasattr(self.format_capabilities, feature) and getattr(self.format_capabilities, feature)
    
    def get_load_options(self) -> Dict[str, Any]:
        """
        Get available loading options for this format.
        
        Returns:
            Dictionary describing available options
        """
        return {}
    
    def get_save_options(self) -> Dict[str, Any]:
        """
        Get available saving options for this format.
        
        Returns:
            Dictionary describing available options
        """
        return {}
    
    def estimate_complexity(self, file_path: Path) -> int:
        """
        Estimate the complexity of processing this file.
        
        Args:
            file_path: Path to the file
        
        Returns:
            Complexity score (higher = more complex)
        """
        try:
            file_size = file_path.stat().st_size
            # Simple heuristic based on file size
            if file_size < 1024:  # < 1KB
                return 1
            elif file_size < 10240:  # < 10KB
                return 2
            elif file_size < 102400:  # < 100KB
                return 3
            elif file_size < 1048576:  # < 1MB
                return 4
            else:
                return 5
        except:
            return 3  # Default complexity
    
    def __str__(self):
        return f"{self.format_name} Handler"
    
    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.format_name}>"