"""
Handler for plain text (.txt) files with support for various common
localization formats.
"""

import re
import chardet
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base.format_handler import FormatHandler, FormatCapabilities, ValidationResult, FormatHandlerError
from ..base.translation_unit import TranslationUnit, TranslationStatus


class TXTHandler(FormatHandler):
    """
    Handles plain text files, attempting to detect and parse common
    localization formats like line-by-line, key-value, and paragraph-based.
    """

    @property
    def format_name(self) -> str:
        return "Plain Text"

    @property
    def file_extensions(self) -> List[str]:
        return [".txt"]

    @property
    def mime_types(self) -> List[str]:
        return ["text/plain"]

    @property
    def format_capabilities(self) -> FormatCapabilities:
        capabilities = FormatCapabilities()
        capabilities.supports_context = True
        capabilities.supports_translation_status = True
        capabilities.preserves_structure = True
        capabilities.supports_placeholders = True
        return capabilities

    def can_handle(self, file_path: Path, content_sample: bytes = None) -> bool:
        """
        Detects if the file is a .txt file.
        Further content-based detection is done during loading.
        """
        return file_path.suffix.lower() in self.file_extensions

    def load(self, file_path: Path, **options) -> List[TranslationUnit]:
        """
        Loads translation units from a plain text file.
        Detects format (line-by-line, key-value, paragraph) automatically.
        """
        encoding = options.get('encoding', self._detect_encoding(file_path))
        
        try:
            with open(file_path, 'r', encoding=encoding, newline='') as f:
                content = f.read()
                line_ending = f.newlines if isinstance(f.newlines, str) else '\n'
        except (UnicodeDecodeError, PermissionError, IOError) as e:
            raise FormatHandlerError(f"Failed to read {file_path} with encoding {encoding}: {e}") from e

        format_type, separator = self._detect_format(content)
        
        units = []
        if format_type == 'key_value':
            units = self._parse_key_value(content, separator)
        elif format_type == 'paragraph':
            units = self._parse_paragraphs(content)
        else: # Fallback to line-by-line
            units = self._parse_lines(content)

        for unit in units:
            unit.attributes['encoding'] = encoding
            unit.attributes['format_type'] = format_type
            unit.attributes['line_ending'] = line_ending
            if separator:
                unit.attributes['separator'] = separator

        return units

    def save(self, units: List[TranslationUnit], file_path: Path, **options) -> None:
        """
        Saves translation units back to a plain text file, preserving the
        original structure.
        """
        if not units:
            return

        # Use attributes from the first unit to determine saving strategy
        first_unit_attrs = units[0].attributes
        encoding = first_unit_attrs.get('encoding', 'utf-8')
        format_type = first_unit_attrs.get('format_type', 'line-by-line')
        line_ending = first_unit_attrs.get('line_ending', '\n')
        separator = first_unit_attrs.get('separator', ': ')

        try:
            with open(file_path, 'w', encoding=encoding, newline=line_ending) as f:
                if format_type == 'key_value':
                    for unit in units:
                        if unit.source or unit.target: # Preserve empty lines if they were loaded
                            f.write(f"{unit.context}{separator}{unit.target or unit.source}\n")
                        else:
                            f.write("\n")
                elif format_type == 'paragraph':
                    f.write(line_ending.join(unit.target or unit.source for unit in units))
                else: # line-by-line
                    f.write(line_ending.join(unit.target or unit.source for unit in units))
        except IOError as e:
            raise FormatHandlerError(f"Failed to write to {file_path}: {e}")

    def validate(self, units: List[TranslationUnit]) -> ValidationResult:
        """
        Validates that the text units are consistent.
        """
        result = super().validate(units)
        if not units:
            return result

        first_unit_attrs = units[0].attributes
        format_type = first_unit_attrs.get('format_type')

        for i, unit in enumerate(units, 1):
            if unit.attributes.get('format_type') != format_type:
                result.add_warning(f"Unit {i} has a different format type than the first unit.")
            if format_type == 'key_value' and not unit.context:
                 result.add_warning(f"Unit {i} is missing a key for key-value format.")
        
        return result

    def _detect_encoding(self, file_path: Path) -> str:
        """Detects file encoding using chardet."""
        with open(file_path, 'rb') as f:
            raw_data = f.read(1024) # Read first 1KB for detection
        
        # Handle BOM
        if raw_data.startswith(b'\xef\xbb\xbf'):
            return 'utf-8-sig'
        if raw_data.startswith(b'\xff\xfe'):
            return 'utf-16-le'
        if raw_data.startswith(b'\xfe\xff'):
            return 'utf-16-be'

        # This is a more aggressive binary detection.
        # If any byte falls outside the common ASCII printable range and it's not
        # a common whitespace/control character, then it's likely binary.
        text_friendly_control_chars = {0x09, 0x0A, 0x0D}  # Tab, LF, CR
        for byte_val in raw_data:
            if not (0x20 <= byte_val <= 0x7E or byte_val in text_friendly_control_chars):
                # If it's outside printable ASCII and not a text-friendly control char,
                # check if it's a non-text control character.
                if not (0x00 <= byte_val <= 0x08 or 0x0B <= byte_val <= 0x0C or 0x0E <= byte_val <= 0x1F):
                    # This is likely a binary byte.
                    raise FormatHandlerError(
                        f"File {file_path} appears to be binary (contains non-text byte 0x{byte_val:02x}). "
                        "Cannot be processed as plain text."
                    )

        # Try decoding as UTF-8 first, as it's the most common and strict.
        try:
            raw_data.decode('utf-8')
            return 'utf-8'
        except UnicodeDecodeError:
            pass  # Not UTF-8, proceed to chardet

        result = chardet.detect(raw_data)
        encoding = result['encoding']
        confidence = result['confidence']

        # If chardet provides a confident encoding, use it.
        if encoding and confidence > 0.7:
            return encoding
        
        # If chardet is not confident, try a fallback like latin-1
        try:
            raw_data.decode('latin-1')
            return 'latin-1'
        except UnicodeDecodeError:
            # If it can't be decoded even with latin-1, it's likely binary
            raise FormatHandlerError(f"File {file_path} appears to be binary or has an unsupported encoding. Cannot be processed as plain text.")

    def _detect_format(self, content: str) -> (str, Optional[str]):
        """Analyzes content to determine the most likely text format."""
        lines = content.splitlines()
        if not lines:
            return 'line-by-line', None

        # Check for key-value patterns
        key_value_pattern = re.compile(r'^\s*([^:=]+)\s*([:=])\s*(.*)$')
        key_value_count = 0
        separators = {}
        for line in lines[:50]: # Check first 50 lines
            if not line.strip(): continue
            match = key_value_pattern.match(line)
            if match:
                key_value_count += 1
                sep = match.group(2)
                separators[sep] = separators.get(sep, 0) + 1

        if key_value_count / (len([l for l in lines[:50] if l.strip()]) or 1) > 0.6:
            # More than 60% of lines look like key-value pairs
            dominant_separator = max(separators, key=separators.get) if separators else ':'
            return 'key_value', dominant_separator + ' '

        # Check for paragraphs (separated by blank lines)
        if '\n\n' in content or '\r\n\r\n' in content:
            return 'paragraph', None

        return 'line-by-line', None

    def _parse_lines(self, content: str) -> List[TranslationUnit]:
        """Parses content as a simple list of lines."""
        units = []
        lines = content.splitlines()
        for i, line in enumerate(lines):
            unit = TranslationUnit()
            unit.id = str(i + 1)
            unit.source = line
            unit.context = f"Line {i + 1}"
            unit.status = TranslationStatus.NEW
            units.append(unit)
        return units

    def _parse_key_value(self, content: str, separator: str) -> List[TranslationUnit]:
        """Parses content as key-value pairs."""
        units = []
        lines = content.splitlines()
        for i, line in enumerate(lines):
            unit = TranslationUnit()
            unit.id = str(i + 1)
            if separator.strip() in line:
                key, _, value = line.partition(separator.strip())
                unit.source = value.strip()
                unit.context = key.strip()
            else:
                # Preserve lines that don't match the format (e.g., comments, empty lines)
                unit.source = line 
                unit.context = f"L{i+1}_COMMENT" # Special context for non-kv lines
            
            unit.status = TranslationStatus.NEW if unit.source else TranslationStatus.TRANSLATED
            units.append(unit)
        return units

    def _parse_paragraphs(self, content: str) -> List[TranslationUnit]:
        """Parses content as paragraphs separated by blank lines."""
        units = []
        # Normalize line endings for consistent splitting
        content = content.replace('\r\n', '\n').replace('\r', '\n')
        paragraphs = content.split('\n\n')
        for i, para in enumerate(paragraphs):
            if not para.strip():
                continue
            unit = TranslationUnit()
            unit.id = str(i + 1)
            unit.source = para.strip()
            unit.context = f"Paragraph {i + 1}"
            unit.status = TranslationStatus.NEW
            units.append(unit)
        return units