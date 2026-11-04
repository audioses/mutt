"""
Central coordinator for all format operations.
"""

from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from .registry import FormatRegistry
from .detector import FormatDetector
from .format_handler import FormatHandler, FormatHandlerError, ValidationError
from .translation_unit import TranslationUnit


class FormatManager:
    """
    Central coordinator for all format operations.
    
    This class provides a high-level interface for loading and saving translation
    files using the extensible format handler system. It manages the registry,
    detector, and coordinates between different handlers.
    """
    
    def __init__(self, registry: FormatRegistry = None):
        """
        Initialize the format manager.
        
        Args:
            registry: Optional FormatRegistry instance. Uses global registry if None.
        """
        if registry is None:
            from .registry import format_registry
            self.registry = format_registry
        else:
            self.registry = registry
            
        self.detector = FormatDetector(self.registry)
        self._initialized = False
        
        # Initialize built-in handlers on first use
        self._ensure_initialized()
    
    def _ensure_initialized(self):
        """Ensure the format system is initialized with built-in handlers."""
        if self._initialized:
            return
        
        try:
            # Auto-discover format handlers
            discovered = self.registry.auto_discover("format_handlers")
            print(f"FormatManager initialized with {discovered} handlers")
        except Exception as e:
            print(f"Warning: Auto-discovery failed: {e}")
        
        self._initialized = True
    
    def load_file(self, file_path: Path, handler_name: str = None, **options) -> Tuple[List[TranslationUnit], FormatHandler]:
        """
        Load translation units from a file.
        
        Args:
            file_path: Path to the file to load
            handler_name: Optional specific handler name to use
            **options: Format-specific loading options
        
        Returns:
            Tuple of (translation_units, handler_used)
        
        Raises:
            FormatHandlerError: If loading fails
            ValueError: If no suitable handler found
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Get handler
        if handler_name:
            handler = self.registry.get_handler(handler_name)
            if not handler:
                raise ValueError(f"Unknown format handler: {handler_name}")
        else:
            handler, confidence = self.detector.detect_format(file_path)
            if not handler:
                raise ValueError(f"Cannot determine format for file: {file_path}")
            
            print(f"Detected format: {handler.format_name} (confidence: {confidence:.2f})")
        
        # Load the file
        try:
            print(f"Loading {file_path} with {handler.format_name} handler...")
            units = handler.load(file_path, **options)
            
            # Enrich units with format metadata
            file_metadata = handler.get_metadata(file_path)
            for unit in units:
                if not unit.original_format:
                    unit.original_format = handler.format_name
                unit.format_metadata.update(file_metadata)
            
            print(f"Successfully loaded {len(units)} translation units")
            return units, handler
            
        except Exception as e:
            raise FormatHandlerError(f"Error loading {file_path} with {handler.format_name}: {e}")
    
    def save_file(self, units: List[TranslationUnit], file_path: Path, 
                  handler_name: str = None, validate: bool = True, **options) -> None:
        """
        Save translation units to a file.
        
        Args:
            units: List of TranslationUnit objects to save
            file_path: Path where to save the file
            handler_name: Optional specific handler name to use
            validate: Whether to validate units before saving
            **options: Format-specific saving options
        
        Raises:
            FormatHandlerError: If saving fails
            ValidationError: If validation fails
            ValueError: If no suitable handler found
        """
        if not units:
            raise ValueError("No translation units to save")
        
        file_path = Path(file_path)
        
        # Get handler
        handler = None
        if handler_name:
            handler = self.registry.get_handler(handler_name)
            if not handler:
                raise ValueError(f"Unknown format handler: {handler_name}")
        else:
            # Try to determine from original format or file extension
            original_format = units[0].original_format if units else None
            if original_format:
                handler = self.registry.get_handler_by_format_name(original_format)
            
            if not handler:
                # Fall back to extension-based detection
                handlers = self.registry.get_handlers_for_extension(file_path.suffix)
                handler = handlers[0] if handlers else None
            
            if not handler:
                raise ValueError(f"Cannot determine format handler for: {file_path}")
        
        # Validate before saving if requested
        if validate:
            validation = handler.validate(units)
            if not validation.is_valid:
                raise ValidationError(f"Validation failed: {'; '.join(validation.errors)}")
            
            if validation.warnings:
                print(f"Validation warnings: {'; '.join(validation.warnings)}")
        
        # Save the file
        try:
            print(f"Saving {len(units)} units to {file_path} with {handler.format_name} handler...")
            
            # Create parent directories if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            handler.save(units, file_path, **options)
            print(f"Successfully saved to {file_path}")
            
        except Exception as e:
            raise FormatHandlerError(f"Error saving {file_path} with {handler.format_name}: {e}")
    
    def get_supported_formats(self) -> Dict[str, FormatHandler]:
        """
        Get all supported formats.
        
        Returns:
            Dictionary mapping format names to handlers
        """
        return {handler.format_name: handler for handler in self.registry.get_all_handlers()}
    
    def get_format_capabilities(self, format_name: str) -> Optional[Dict[str, bool]]:
        """
        Get capabilities for a specific format.
        
        Args:
            format_name: Name of the format
        
        Returns:
            Dictionary of capabilities or None if format not found
        """
        handler = self.registry.get_handler_by_format_name(format_name)
        return handler.format_capabilities.to_dict() if handler else None
    
    def get_file_dialog_wildcard(self, extra_extensions=()) -> str:
        """
        Build file dialog wildcard string for all supported formats.

        Args:
            extra_extensions: extra extensions (e.g. ['.mutt']) folded into the
                "All Supported Files" filter, for files no handler owns

        Returns:
            Wildcard string suitable for wx.FileDialog
        """
        formats = self.get_supported_formats()
        wildcards = []
        all_extensions = [f"*{ext}" for ext in extra_extensions]

        for format_name, handler in formats.items():
            extensions = [f"*{ext}" for ext in handler.file_extensions]
            all_extensions.extend(extensions)
            wildcards.append(f"{format_name} ({';'.join(extensions)})|{';'.join(extensions)}")
        
        # Add "All Supported" at the beginning
        if all_extensions:
            all_wildcard = f"All Supported Files ({';'.join(all_extensions)})|{';'.join(all_extensions)}"
            wildcards.insert(0, all_wildcard)
        
        # Add "All Files" at the end
        wildcards.append("All Files (*.*)|*.*")
        
        return "|".join(wildcards)
    
    def detect_file_format(self, file_path: Path) -> Optional[str]:
        """
        Detect the format of a file.
        
        Args:
            file_path: Path to the file
        
        Returns:
            Format name or None if not detected
        """
        handler, confidence = self.detector.detect_format(file_path)
        return handler.format_name if handler else None
    
    def get_detection_info(self, file_path: Path) -> Dict[str, Any]:
        """
        Get detailed format detection information.
        
        Args:
            file_path: Path to the file
        
        Returns:
            Dictionary with detection details
        """
        return self.detector.get_detection_info(file_path)
    
    def validate_file(self, file_path: Path, handler_name: str = None) -> Dict[str, Any]:
        """
        Validate a translation file without loading all units.
        
        Args:
            file_path: Path to the file to validate
            handler_name: Optional specific handler to use
        
        Returns:
            Dictionary with validation results
        """
        try:
            units, handler = self.load_file(file_path, handler_name)
            validation = handler.validate(units)
            
            return {
                'valid': validation.is_valid,
                'errors': validation.errors,
                'warnings': validation.warnings,
                'unit_count': len(units),
                'handler': handler.format_name,
                'file_size': file_path.stat().st_size
            }
        except Exception as e:
            return {
                'valid': False,
                'errors': [str(e)],
                'warnings': [],
                'unit_count': 0,
                'handler': None,
                'file_size': file_path.stat().st_size if file_path.exists() else 0
            }
    
    def convert_file(self, source_path: Path, target_path: Path, 
                     source_handler: str = None, target_handler: str = None,
                     **options) -> Dict[str, Any]:
        """
        Convert a file from one format to another.
        
        Args:
            source_path: Path to source file
            target_path: Path to target file
            source_handler: Optional source format handler name
            target_handler: Optional target format handler name
            **options: Format-specific options
        
        Returns:
            Dictionary with conversion results
        """
        try:
            # Load from source
            units, source_handler_obj = self.load_file(source_path, source_handler)
            
            # Save to target
            self.save_file(units, target_path, target_handler, **options)
            
            return {
                'success': True,
                'source_format': source_handler_obj.format_name,
                'target_format': self.detect_file_format(target_path),
                'unit_count': len(units),
                'source_size': source_path.stat().st_size,
                'target_size': target_path.stat().st_size
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'source_format': None,
                'target_format': None,
                'unit_count': 0,
                'source_size': source_path.stat().st_size if source_path.exists() else 0,
                'target_size': 0
            }
    
    def get_handler_info(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information about all registered handlers.
        
        Returns:
            Dictionary with handler information
        """
        return self.registry.get_handler_info()
    
    def register_handler(self, handler_class) -> None:
        """
        Register a new format handler.
        
        Args:
            handler_class: FormatHandler subclass to register
        """
        self.registry.register(handler_class)
    
    def __str__(self):
        return f"FormatManager({len(self.registry)} handlers)"
    
    def __repr__(self):
        return f"<FormatManager: {len(self.registry)} handlers>"