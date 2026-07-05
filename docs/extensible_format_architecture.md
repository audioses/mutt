# MUTT Extensible Format Handler Architecture

## Executive Summary

This document outlines a comprehensive extensible format handler architecture for MUTT that supports the extensive list of translation file formats while providing a universal internal format with rich metadata support for future features like comments, notes, review workflows, and approval states.

## Current State Analysis

### Current Format Support
- **PO files**: Using `polib` library
- **XLIFF 1.2/2.0**: Custom XML parsing with namespace handling
- **JSON**: Key-value pairs and structured objects
- **CSV**: Auto-detection of source/target columns
- **TXT**: Line-based entries

### Current Internal Format
```python
{"msgid": "source", "msgstr": "target", "unit_id": "optional"}
```

### Current Limitations
1. **Hardcoded format handling** in `main.py` methods
2. **Limited metadata** capture
3. **No extensibility** mechanism for new formats
4. **Format-specific logic** scattered throughout codebase
5. **No validation** or error recovery framework

## 1. Universal Internal Format Design

```python
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional

class TranslationUnit:
    """
    Universal internal representation of a translation unit with extensible metadata
    """
    def __init__(self):
        # Core translation data
        self.id: str = ""                    # Unique identifier within file
        self.source: str = ""                # Source text
        self.target: str = ""                # Target text
        self.source_language: str = ""       # Source language code
        self.target_language: str = ""       # Target language code
        
        # Status and workflow
        self.status: TranslationStatus = TranslationStatus.NEW
        self.reviewed: bool = False
        self.approved: bool = False
        self.locked: bool = False
        
        # Metadata and context
        self.context: str = ""               # Context or comment
        self.notes: List[Note] = []          # Translator/reviewer notes
        self.max_length: Optional[int] = None # Character limit
        self.placeholders: List[str] = []    # Variables like {name}
        
        # Quality and confidence
        self.quality_score: Optional[float] = None
        self.confidence: Optional[float] = None
        self.fuzzy: bool = False
        
        # Timestamps and tracking
        self.created_at: Optional[datetime] = None
        self.updated_at: Optional[datetime] = None
        self.translated_by: Optional[str] = None
        self.reviewed_by: Optional[str] = None
        
        # Format-specific attributes (extensible)
        self.attributes: Dict[str, Any] = {}
        
        # Original format preservation
        self.original_format: Optional[str] = None
        self.format_metadata: Dict[str, Any] = {}

class TranslationStatus(Enum):
    NEW = "new"
    TRANSLATED = "translated" 
    REVIEWED = "reviewed"
    APPROVED = "approved"
    NEEDS_WORK = "needs_work"
    FINAL = "final"

class Note:
    def __init__(self, text: str, author: str = "", timestamp: datetime = None):
        self.text = text
        self.author = author
        self.timestamp = timestamp or datetime.now()
        self.type: NoteType = NoteType.GENERAL

class NoteType(Enum):
    GENERAL = "general"
    INSTRUCTION = "instruction"
    ERROR = "error"
    QUESTION = "question"
    TERMINOLOGY = "terminology"
```

## 2. FormatHandler Base Class

```python
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, BinaryIO, TextIO
from pathlib import Path

class FormatHandler(ABC):
    """
    Abstract base class for all format handlers
    """
    
    @property
    @abstractmethod
    def format_name(self) -> str:
        """Human-readable format name"""
        pass
    
    @property
    @abstractmethod
    def file_extensions(self) -> List[str]:
        """Supported file extensions (e.g., ['.po', '.pot'])"""
        pass
    
    @property
    @abstractmethod
    def mime_types(self) -> List[str]:
        """Supported MIME types"""
        pass
    
    @property
    @abstractmethod
    def format_capabilities(self) -> FormatCapabilities:
        """What features this format supports"""
        pass
    
    # Core methods
    @abstractmethod
    def can_handle(self, file_path: Path, content_sample: bytes = None) -> bool:
        """Determine if this handler can process the given file"""
        pass
    
    @abstractmethod
    def load(self, file_path: Path, **options) -> List[TranslationUnit]:
        """Load translation units from file"""
        pass
    
    @abstractmethod
    def save(self, units: List[TranslationUnit], file_path: Path, **options) -> None:
        """Save translation units to file"""
        pass
    
    # Optional methods with default implementations
    def validate(self, units: List[TranslationUnit]) -> ValidationResult:
        """Validate translation units for this format"""
        return ValidationResult(is_valid=True, errors=[], warnings=[])
    
    def get_metadata(self, file_path: Path) -> Dict[str, Any]:
        """Extract file-level metadata"""
        return {}
    
    def supports_feature(self, feature: str) -> bool:
        """Check if handler supports specific feature"""
        return hasattr(self.format_capabilities, feature) and getattr(self.format_capabilities, feature)

class FormatCapabilities:
    """Defines what features a format supports"""
    def __init__(self):
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

class ValidationResult:
    def __init__(self, is_valid: bool, errors: List[str] = None, warnings: List[str] = None):
        self.is_valid = is_valid
        self.errors = errors or []
        self.warnings = warnings or []
```

## 3. FormatRegistry System

```python
import importlib
import pkgutil
from typing import Type, Dict, List
from pathlib import Path

class FormatRegistry:
    """
    Dynamic registry for format handlers with plugin-style loading
    """
    
    def __init__(self):
        self._handlers: Dict[str, Type[FormatHandler]] = {}
        self._handler_instances: Dict[str, FormatHandler] = {}
        self._extension_map: Dict[str, List[str]] = {}  # extension -> handler_names
        self._mime_map: Dict[str, List[str]] = {}       # mime_type -> handler_names
    
    def register(self, handler_class: Type[FormatHandler]) -> None:
        """Register a format handler class"""
        handler = handler_class()
        handler_name = handler.format_name.lower().replace(' ', '_')
        
        self._handlers[handler_name] = handler_class
        self._handler_instances[handler_name] = handler
        
        # Build lookup maps
        for ext in handler.file_extensions:
            ext_lower = ext.lower()
            if ext_lower not in self._extension_map:
                self._extension_map[ext_lower] = []
            self._extension_map[ext_lower].append(handler_name)
        
        for mime_type in handler.mime_types:
            if mime_type not in self._mime_map:
                self._mime_map[mime_type] = []
            self._mime_map[mime_type].append(handler_name)
    
    def auto_discover(self, package_path: str = "format_handlers") -> None:
        """Automatically discover and load format handlers from a package"""
        try:
            package = importlib.import_module(package_path)
            for _, module_name, _ in pkgutil.iter_modules(package.__path__):
                module = importlib.import_module(f"{package_path}.{module_name}")
                
                # Look for FormatHandler subclasses
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and 
                        issubclass(attr, FormatHandler) and 
                        attr != FormatHandler):
                        self.register(attr)
        except ImportError:
            pass  # Package doesn't exist yet
    
    def get_handlers_for_extension(self, extension: str) -> List[FormatHandler]:
        """Get handlers that support a file extension"""
        ext_lower = extension.lower()
        if not ext_lower.startswith('.'):
            ext_lower = '.' + ext_lower
        
        handler_names = self._extension_map.get(ext_lower, [])
        return [self._handler_instances[name] for name in handler_names]
    
    def get_handlers_for_mime(self, mime_type: str) -> List[FormatHandler]:
        """Get handlers that support a MIME type"""
        handler_names = self._mime_map.get(mime_type, [])
        return [self._handler_instances[name] for name in handler_names]
    
    def get_all_handlers(self) -> List[FormatHandler]:
        """Get all registered handlers"""
        return list(self._handler_instances.values())
    
    def get_handler(self, name: str) -> Optional[FormatHandler]:
        """Get a specific handler by name"""
        return self._handler_instances.get(name.lower().replace(' ', '_'))

# Global registry instance
format_registry = FormatRegistry()
```

## 4. FormatDetector System

```python
import mimetypes
import magic  # python-magic library
from typing import Optional, Tuple, List

class FormatDetector:
    """
    Intelligent format detection using multiple strategies
    """
    
    def __init__(self, registry: FormatRegistry):
        self.registry = registry
        try:
            self.magic_detector = magic.Magic(mime=True)
        except:
            self.magic_detector = None  # Fallback if magic not available
    
    def detect_format(self, file_path: Path, content_sample: bytes = None) -> Tuple[Optional[FormatHandler], float]:
        """
        Detect the best format handler for a file
        Returns (handler, confidence_score)
        """
        if not content_sample:
            with open(file_path, 'rb') as f:
                content_sample = f.read(8192)  # Read first 8KB
        
        candidates = []
        
        # Strategy 1: File extension
        extension = file_path.suffix.lower()
        ext_handlers = self.registry.get_handlers_for_extension(extension)
        for handler in ext_handlers:
            if handler.can_handle(file_path, content_sample):
                candidates.append((handler, 0.8))  # High confidence for extension match
        
        # Strategy 2: MIME type detection
        if self.magic_detector:
            try:
                mime_type = self.magic_detector.from_buffer(content_sample)
                mime_handlers = self.registry.get_handlers_for_mime(mime_type)
                for handler in mime_handlers:
                    if handler.can_handle(file_path, content_sample):
                        candidates.append((handler, 0.9))  # Very high confidence for MIME match
            except:
                pass
        
        # Strategy 3: Content analysis fallback
        if not candidates:
            for handler in self.registry.get_all_handlers():
                if handler.can_handle(file_path, content_sample):
                    candidates.append((handler, 0.6))  # Lower confidence for content-only match
        
        # Return best candidate
        if candidates:
            return max(candidates, key=lambda x: x[1])
        
        return None, 0.0
    
    def detect_multiple_formats(self, file_path: Path) -> List[Tuple[FormatHandler, float]]:
        """Get all possible format handlers ranked by confidence"""
        with open(file_path, 'rb') as f:
            content_sample = f.read(8192)
        
        candidates = []
        
        # Check all handlers
        for handler in self.registry.get_all_handlers():
            if handler.can_handle(file_path, content_sample):
                confidence = 0.5  # Base confidence
                
                # Boost confidence based on matches
                if file_path.suffix.lower() in handler.file_extensions:
                    confidence += 0.3
                
                if self.magic_detector:
                    try:
                        mime_type = self.magic_detector.from_buffer(content_sample)
                        if mime_type in handler.mime_types:
                            confidence += 0.4
                    except:
                        pass
                
                candidates.append((handler, min(confidence, 1.0)))
        
        return sorted(candidates, key=lambda x: x[1], reverse=True)
```

## 5. FormatManager - Central Coordinator

```python
class FormatManager:
    """
    Central coordinator for all format operations
    """
    
    def __init__(self):
        self.registry = FormatRegistry()
        self.detector = FormatDetector(self.registry)
        self._initialize_builtin_handlers()
    
    def _initialize_builtin_handlers(self):
        """Initialize built-in format handlers"""
        self.registry.auto_discover("format_handlers")
        
        # Register any handlers that couldn't be auto-discovered
        # This would be called during app initialization
    
    def load_file(self, file_path: Path, handler_name: str = None, **options) -> Tuple[List[TranslationUnit], FormatHandler]:
        """
        Load translation units from a file
        """
        file_path = Path(file_path)
        
        if handler_name:
            handler = self.registry.get_handler(handler_name)
            if not handler:
                raise ValueError(f"Unknown format handler: {handler_name}")
        else:
            handler, confidence = self.detector.detect_format(file_path)
            if not handler:
                raise ValueError(f"Cannot determine format for file: {file_path}")
        
        try:
            units = handler.load(file_path, **options)
            
            # Enrich units with format metadata
            for unit in units:
                if not unit.original_format:
                    unit.original_format = handler.format_name
                unit.format_metadata.update(handler.get_metadata(file_path))
            
            return units, handler
        except Exception as e:
            raise FormatHandlerError(f"Error loading {file_path} with {handler.format_name}: {e}")
    
    def save_file(self, units: List[TranslationUnit], file_path: Path, handler_name: str = None, **options) -> None:
        """
        Save translation units to a file
        """
        file_path = Path(file_path)
        
        if handler_name:
            handler = self.registry.get_handler(handler_name)
        else:
            # Try to determine from original format or file extension
            original_format = units[0].original_format if units else None
            if original_format:
                handler = self.registry.get_handler(original_format)
            else:
                handlers = self.registry.get_handlers_for_extension(file_path.suffix)
                handler = handlers[0] if handlers else None
        
        if not handler:
            raise ValueError(f"Cannot determine format handler for: {file_path}")
        
        # Validate before saving
        validation = handler.validate(units)
        if not validation.is_valid:
            raise ValidationError(f"Validation failed: {validation.errors}")
        
        try:
            handler.save(units, file_path, **options)
        except Exception as e:
            raise FormatHandlerError(f"Error saving {file_path} with {handler.format_name}: {e}")
    
    def get_supported_formats(self) -> Dict[str, FormatHandler]:
        """Get all supported formats"""
        return {handler.format_name: handler for handler in self.registry.get_all_handlers()}
    
    def get_format_capabilities(self, format_name: str) -> Optional[FormatCapabilities]:
        """Get capabilities for a specific format"""
        handler = self.registry.get_handler(format_name)
        return handler.format_capabilities if handler else None

class FormatHandlerError(Exception):
    pass

class ValidationError(Exception):
    pass
```

## 6. Directory Structure

```
format_handlers/
├── __init__.py
├── base/
│   ├── __init__.py
│   ├── format_handler.py          # Base classes
│   ├── translation_unit.py        # Universal format
│   ├── registry.py                # Registry system
│   ├── detector.py                # Format detection
│   └── manager.py                 # Central coordinator
├── localization/
│   ├── __init__.py
│   ├── po_handler.py              # GNU Gettext PO/POT
│   ├── xliff_handler.py           # XLIFF 1.2/2.0/2.1
│   ├── xliff12_handler.py         # XLIFF 1.2 specific
│   ├── xliff20_handler.py         # XLIFF 2.0/2.1 specific
│   ├── tmx_handler.py             # Translation Memory eXchange
│   ├── ts_handler.py              # Qt Linguist
│   └── resx_handler.py            # .NET Resources
├── development/
│   ├── __init__.py
│   ├── json_handler.py            # JSON key-value
│   ├── properties_handler.py      # Java Properties
│   ├── rc_handler.py              # Windows Resources
│   ├── php_handler.py             # PHP Arrays
│   └── js_handler.py              # JavaScript i18n
├── documentation/
│   ├── __init__.py
│   ├── html_handler.py            # HTML with i18n
│   ├── xml_handler.py             # Generic XML
│   ├── dita_handler.py            # DITA formats
│   ├── docbook_handler.py         # DocBook
│   └── markdown_handler.py        # Markdown with i18n
├── office/
│   ├── __init__.py
│   ├── docx_handler.py            # Microsoft Word
│   ├── xlsx_handler.py            # Microsoft Excel
│   ├── pptx_handler.py            # Microsoft PowerPoint
│   ├── odt_handler.py             # OpenDocument Text
│   └── ods_handler.py             # OpenDocument Spreadsheet
├── desktop_publishing/
│   ├── __init__.py
│   ├── idml_handler.py            # InDesign Markup
│   ├── inx_handler.py             # InDesign Interchange
│   ├── icml_handler.py            # InCopy Markup
│   ├── mif_handler.py             # Maker Interchange Format
│   └── svg_handler.py             # SVG graphics
├── multimedia/
│   ├── __init__.py
│   ├── srt_handler.py             # SubRip subtitles
│   ├── vtt_handler.py             # WebVTT subtitles
│   ├── sbv_handler.py             # YouTube subtitles
│   └── ass_handler.py             # Advanced SubStation Alpha
├── proprietary/
│   ├── __init__.py
│   ├── sdlxliff_handler.py        # Trados SDLXLIFF
│   ├── sdlppx_handler.py          # Trados packages
│   ├── txml_handler.py            # GlobalLink TXML
│   ├── txlf_handler.py            # GlobalLink XLIFF
│   ├── mqxliff_handler.py         # MemoQ XLIFF
│   └── wpml_handler.py            # WordPress WPML
└── generic/
    ├── __init__.py
    ├── csv_handler.py             # Comma Separated Values
    ├── tsv_handler.py             # Tab Separated Values
    ├── txt_handler.py             # Plain text
    └── binary_handler.py          # Binary format base
```

## 7. Integration with Current System

### Modified main.py Integration

```python
# Modified main.py integration
class MainFrame(wx.Frame):
    def __init__(self, parent, title):
        super().__init__(parent, title=title)
        
        # Initialize format system
        self.format_manager = FormatManager()
        
        # Compatibility attributes
        self.translation_units: List[TranslationUnit] = []
        self.current_handler: Optional[FormatHandler] = None
        
        # Rest of initialization...
    
    def on_open_file(self, event):
        """Updated file opening with format handler system"""
        wildcard = self._build_file_wildcard()
        
        with wx.FileDialog(self, "Open Translation File", wildcard=wildcard, 
                          style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                file_path = Path(dlg.GetPath())
                try:
                    # Use format manager instead of hardcoded handlers
                    self.translation_units, self.current_handler = self.format_manager.load_file(file_path)
                    self.po_file_path = str(file_path)
                    
                    # Convert to current internal format for compatibility
                    self.all_po_entries = [self._unit_to_legacy_format(unit) for unit in self.translation_units]
                    
                    self.show_translation_interface()
                except Exception as e:
                    wx.MessageBox(f"Error loading file: {e}", "Error", wx.OK | wx.ICON_ERROR)
    
    def _build_file_wildcard(self) -> str:
        """Build file dialog wildcard from registered handlers"""
        formats = self.format_manager.get_supported_formats()
        wildcards = []
        all_extensions = []
        
        for format_name, handler in formats.items():
            extensions = [f"*{ext}" for ext in handler.file_extensions]
            all_extensions.extend(extensions)
            wildcards.append(f"{format_name} ({';'.join(extensions)})|{';'.join(extensions)}")
        
        # Add "All Supported" at the beginning
        all_wildcard = f"All Supported Files ({';'.join(all_extensions)})|{';'.join(all_extensions)}"
        wildcards.insert(0, all_wildcard)
        
        # Add "All Files" at the end
        wildcards.append("All Files (*.*)|*.*")
        
        return "|".join(wildcards)
    
    def _unit_to_legacy_format(self, unit: TranslationUnit) -> Dict[str, str]:
        """Convert TranslationUnit to legacy format for backward compatibility"""
        return {
            "msgid": unit.source,
            "msgstr": unit.target,
            "unit_id": unit.id
        }
    
    def on_save_changes(self, event):
        """Updated save with format handler system"""
        if not self.translation_units:
            return
        
        # Convert legacy format back to TranslationUnits
        updated_units = []
        for i, legacy_entry in enumerate(self.all_po_entries):
            if i < len(self.translation_units):
                unit = self.translation_units[i]
                unit.target = legacy_entry["msgstr"]
                updated_units.append(unit)
        
        # Save using format manager
        output_path = self._get_output_path()
        try:
            self.format_manager.save_file(updated_units, output_path, 
                                        handler_name=self.current_handler.format_name)
            wx.MessageBox(f"Saved to: {output_path}", "Success", wx.OK | wx.ICON_INFORMATION)
        except Exception as e:
            wx.MessageBox(f"Error saving: {e}", "Error", wx.OK | wx.ICON_ERROR)
```

## 8. Example Format Handler Implementation

### PO Handler Example

```python
# format_handlers/localization/po_handler.py
import polib
from pathlib import Path
from typing import List
from ..base.format_handler import FormatHandler, FormatCapabilities
from ..base.translation_unit import TranslationUnit, TranslationStatus, Note

class POHandler(FormatHandler):
    """Handler for GNU Gettext PO/POT files"""
    
    @property
    def format_name(self) -> str:
        return "GNU Gettext PO"
    
    @property
    def file_extensions(self) -> List[str]:
        return ['.po', '.pot']
    
    @property
    def mime_types(self) -> List[str]:
        return ['text/x-gettext-translation', 'text/x-po']
    
    @property
    def format_capabilities(self) -> FormatCapabilities:
        caps = FormatCapabilities()
        caps.supports_comments = True
        caps.supports_context = True
        caps.supports_plural_forms = True
        caps.supports_fuzzy_matching = True
        caps.supports_translation_status = True
        caps.supports_file_metadata = True
        return caps
    
    def can_handle(self, file_path: Path, content_sample: bytes = None) -> bool:
        """Check if this is a valid PO file"""
        if file_path.suffix.lower() in self.file_extensions:
            return True
        
        if content_sample:
            try:
                content_str = content_sample.decode('utf-8')
                # Look for PO file markers
                po_markers = ['msgid', 'msgstr', '# SOME DESCRIPTIVE TITLE']
                return any(marker in content_str for marker in po_markers)
            except:
                pass
        
        return False
    
    def load(self, file_path: Path, **options) -> List[TranslationUnit]:
        """Load PO file into TranslationUnits"""
        po_file = polib.pofile(str(file_path))
        units = []
        
        for entry in po_file:
            if entry.obsolete:
                continue
                
            unit = TranslationUnit()
            unit.id = entry.msgctxt or f"po_{len(units)}"
            unit.source = entry.msgid
            unit.target = entry.msgstr
            unit.context = entry.msgctxt or ""
            
            # Handle PO-specific attributes
            if entry.comment:
                unit.notes.append(Note(entry.comment, "translator"))
            if entry.tcomment:
                unit.notes.append(Note(entry.tcomment, "developer"))
            
            # Status mapping
            if entry.fuzzy:
                unit.fuzzy = True
                unit.status = TranslationStatus.NEEDS_WORK
            elif entry.msgstr:
                unit.status = TranslationStatus.TRANSLATED
            else:
                unit.status = TranslationStatus.NEW
            
            # Store PO-specific metadata
            unit.attributes['po_flags'] = entry.flags
            unit.attributes['po_occurrences'] = entry.occurrences
            unit.attributes['po_previous_msgid'] = entry.previous_msgid
            
            units.append(unit)
        
        return units
    
    def save(self, units: List[TranslationUnit], file_path: Path, **options) -> None:
        """Save TranslationUnits to PO file"""
        # Load original PO to preserve structure
        try:
            po_file = polib.pofile(str(file_path))
        except:
            po_file = polib.POFile()
        
        # Create lookup map for units
        unit_map = {unit.source: unit for unit in units}
        
        # Update existing entries
        for entry in po_file:
            if entry.msgid in unit_map:
                unit = unit_map[entry.msgid]
                entry.msgstr = unit.target
                
                # Update flags
                entry.flags = []
                if unit.fuzzy:
                    entry.flags.append('fuzzy')
                
                # Restore PO-specific attributes
                if 'po_flags' in unit.attributes:
                    entry.flags.extend(unit.attributes['po_flags'])
        
        # Add new entries
        existing_msgids = {entry.msgid for entry in po_file}
        for unit in units:
            if unit.source not in existing_msgids:
                entry = polib.POEntry(
                    msgid=unit.source,
                    msgstr=unit.target,
                    msgctxt=unit.context or None
                )
                if unit.fuzzy:
                    entry.flags.append('fuzzy')
                po_file.append(entry)
        
        po_file.save(str(file_path))
    
    def get_metadata(self, file_path: Path) -> Dict[str, Any]:
        """Extract PO file metadata"""
        try:
            po_file = polib.pofile(str(file_path))
            return {
                'po_header': dict(po_file.header),
                'po_metadata': po_file.metadata,
                'total_entries': len(po_file),
                'translated_entries': len(po_file.translated_entries()),
                'untranslated_entries': len(po_file.untranslated_entries()),
                'fuzzy_entries': len(po_file.fuzzy_entries())
            }
        except:
            return {}
```

## 9. Architecture Diagrams

### System Overview Mermaid Diagram

```mermaid
graph TB
    subgraph "Application Layer"
        A[MainFrame - GUI]
        B[Translation Interface]
        C[Review Interface]
    end
    
    subgraph "Format System"
        D[FormatManager]
        E[FormatRegistry]
        F[FormatDetector]
    end
    
    subgraph "Format Handlers"
        G[POHandler]
        H[XLIFFHandler]
        I[JSONHandler]
        J[HTMLHandler]
        K[...]
    end
    
    subgraph "Internal Format"
        L[TranslationUnit]
        M[Note]
        N[TranslationStatus]
    end
    
    A --> D
    D --> E
    D --> F
    E --> G
    E --> H
    E --> I
    E --> J
    E --> K