"""
Handler for JSON-based localization files.

Supports:
- Flat key-value structures
- Nested key-value structures
- Arrays for pluralization (simple cases)
- Preserving structure and comments via special keys.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base.format_handler import FormatHandler, FormatCapabilities, ValidationResult, FormatHandlerError
from ..base.translation_unit import TranslationUnit, TranslationStatus

class JSONHandler(FormatHandler):
    """
    Handles localization files stored in JSON format.

    This handler can parse flat and nested JSON files, mapping keys to translation
    units. It preserves the original structure of the JSON file on save.
    """

    @property
    def format_name(self) -> str:
        return "JSON"

    @property
    def file_extensions(self) -> List[str]:
        return [".json"]

    @property
    def mime_types(self) -> List[str]:
        return ["application/json"]

    @property
    def format_capabilities(self) -> FormatCapabilities:
        capabilities = FormatCapabilities()
        capabilities.supports_comments = True  # Via special keys like "_comment"
        capabilities.supports_context = True   # From key paths
        capabilities.supports_plural_forms = True # Simple array support
        capabilities.supports_translation_status = True
        capabilities.preserves_structure = True
        capabilities.supports_attributes = True
        return capabilities

    def can_handle(self, file_path: Path, content_sample: bytes = None) -> bool:
        if file_path.suffix.lower() not in self.file_extensions:
            return False
        
        if content_sample:
            try:
                content_str = content_sample.decode('utf-8').strip()
                # Check if it looks like a JSON object or array
                return content_str.startswith('{') or content_str.startswith('[')
            except UnicodeDecodeError:
                return False
        return True

    def load(self, file_path: Path, **options) -> List[TranslationUnit]:
        file_path = Path(file_path) # Ensure it's a Path object
        try:
            with file_path.open('r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise FormatHandlerError(f"Invalid JSON file: {e}") from e
        except (PermissionError, IOError, Exception) as e:
            raise FormatHandlerError(f"Failed to read file: {e}") from e

        units = []
        self._flatten_json(data, units)
        
        # Store original structure for saving
        for unit in units:
            unit.format_metadata['original_structure'] = data
            unit.original_format = self.format_name

        return units

    def _flatten_json(self, data: Dict[str, Any], units: List[TranslationUnit], parent_key: str = '', comments: Optional[Dict] = None):
        """Recursively parse JSON and create TranslationUnits."""
        local_comments = {k: v for k, v in data.items() if isinstance(k, str) and (k.startswith('_comment_') or k.endswith('_comment'))}
        
        for key, value in data.items():
            if key in local_comments:
                continue

            full_key = f"{parent_key}.{key}" if parent_key else key

            if isinstance(value, dict):
                self._flatten_json(value, units, full_key, local_comments)
            elif isinstance(value, str):
                unit = TranslationUnit()
                unit.id = full_key
                unit.source = value
                unit.context = full_key
                
                comment_key_1 = f"_comment_{key}"
                comment_key_2 = f"{key}_comment"
                if comment_key_1 in local_comments:
                    unit.add_note(local_comments[comment_key_1])
                elif comment_key_2 in local_comments:
                    unit.add_note(local_comments[comment_key_2])

                if unit.is_translated():
                     unit.status = TranslationStatus.TRANSLATED
                
                units.append(unit)
            elif isinstance(value, list) and all(isinstance(v, str) for v in value):
                # Handle simple pluralization (array of strings)
                unit = TranslationUnit()
                unit.id = full_key
                unit.source = " | ".join(value) # Simple representation
                unit.context = full_key
                unit.attributes['plural_forms'] = value
                if unit.is_translated():
                     unit.status = TranslationStatus.TRANSLATED
                units.append(unit)


    def save(self, units: List[TranslationUnit], file_path: Path, **options) -> None:
        file_path = Path(file_path) # Ensure it's a Path object
        if not units:
            # Write empty JSON object if no units
            file_path.write_text('{}', encoding='utf-8')
            return

        # Use the structure from the first unit's metadata
        output_data = units[0].format_metadata.get('original_structure', {})
        
        # Create a dictionary for quick lookup of units by ID
        unit_map = {unit.id: unit for unit in units}

        # Reconstruct the JSON with updated translations
        self._reconstruct_json(output_data, unit_map)

        try:
            with file_path.open('w', encoding='utf-8') as f:
                indent = options.get('indent', 4)
                json.dump(output_data, f, indent=indent, ensure_ascii=False)
        except Exception as e:
            raise FormatHandlerError(f"Failed to write JSON file: {e}")

    def _reconstruct_json(self, data: Dict[str, Any], unit_map: Dict[str, TranslationUnit], parent_key: str = ''):
        """Recursively reconstructs the JSON object with new translations."""
        for key, value in list(data.items()):
            full_key = f"{parent_key}.{key}" if parent_key else key

            if isinstance(value, dict):
                self._reconstruct_json(value, unit_map, full_key)
            elif full_key in unit_map:
                unit = unit_map[full_key]
                if unit.target:
                    if 'plural_forms' in unit.attributes and isinstance(unit.attributes['plural_forms'], list):
                        # Attempt to parse plural forms back from target
                        data[key] = [t.strip() for t in unit.target.split('|')]
                    else:
                        data[key] = unit.target
                else:
                    data[key] = unit.source # Fallback to source if target is empty


    def validate(self, units: List[TranslationUnit]) -> ValidationResult:
        result = super().validate(units)
        
        # Check for duplicate keys
        keys = [unit.id for unit in units]
        if len(keys) != len(set(keys)):
            result.add_error("Duplicate keys found in JSON structure.")
            
        # Check for valid structure preservation
        if units and 'original_structure' not in units[0].format_metadata:
            result.add_warning("Original JSON structure metadata is missing. Saving may result in a flat structure.")
            
        return result