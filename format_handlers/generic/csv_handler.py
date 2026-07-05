"""
Handler for Comma-Separated Values (CSV) translation files.
"""

import csv
import io
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base.format_handler import FormatHandler, FormatCapabilities, ValidationResult, FormatHandlerError
from ..base.translation_unit import TranslationUnit, TranslationStatus

class CSVHandler(FormatHandler):
    """
    Handler for CSV translation files.

    This handler supports various CSV structures, including:
    - Two-column format: (key, translation)
    - Three-column format: (key, source, target)
    - Multi-column format with headers for different languages and comments.
    
    It automatically detects the CSV dialect (delimiter, quoting) and
    preserves the original structure upon saving.
    """

    @property
    def format_name(self) -> str:
        return "CSV (Comma-Separated Values)"

    @property
    def file_extensions(self) -> List[str]:
        return ['.csv']

    @property
    def mime_types(self) -> List[str]:
        return ['text/csv']

    @property
    def format_capabilities(self) -> FormatCapabilities:
        caps = FormatCapabilities()
        caps.supports_comments = True
        caps.supports_context = True
        caps.supports_translation_status = True
        caps.supports_attributes = True
        caps.preserves_structure = True
        return caps

    def can_handle(self, file_path: Path, content_sample: bytes = None) -> bool:
        """
        Check if this handler can potentially process the given file based on extension.
        A more thorough check is performed during the load operation.
        """
        if file_path.suffix.lower() not in self.file_extensions:
            return False
        
        if content_sample:
            try:
                # A very basic check: ensure it's decodable and contains common CSV separators
                content_str = content_sample.decode('utf-8')
                return ',' in content_str or '\t' in content_str or ';' in content_str
            except UnicodeDecodeError:
                return False
        return True

    def load(self, file_path: Path, **options) -> List[TranslationUnit]:
        """Load CSV file into TranslationUnits."""
        file_path = Path(file_path) # Ensure it's a Path object
        units = []
        encoding = options.get('encoding', 'utf-8-sig') # Handle BOM

        try:
            with file_path.open('r', encoding=encoding, newline='') as f:
                content = f.read()
                
            # Sniff dialect
            sniffer = csv.Sniffer()
            try:
                dialect = sniffer.sniff(content[:4096])
                has_header = sniffer.has_header(content[:4096])
            except csv.Error as e:
                # If sniffing fails, fall back to default comma-separated dialect
                dialect = 'excel' # Standard comma-separated dialect
                # Attempt to determine header by checking if the first row contains common header names
                first_line = content.splitlines()[0] if content else ""
                has_header = any(h in first_line.lower() for h in ['key', 'source', 'target', 'comment'])

            reader = csv.reader(io.StringIO(content), dialect)
            
            rows = list(reader)
            if not rows:
                return []

            headers = []
            if has_header:
                headers = [h.lower() for h in rows.pop(0)]
            
            col_map = self._map_columns(headers, rows[0])
            
            if not col_map.get('source_col_idx') is not None and not col_map.get('key_col_idx') is not None:
                 raise ValueError("CSV file must have at least a key or source column.")

            for i, row in enumerate(rows):
                if not any(field.strip() for field in row):
                    continue # Skip empty rows

                unit = TranslationUnit()
                unit.id = self._get_cell(row, col_map.get('key_col_idx')) or f"row-{i+1}"
                unit.source = self._get_cell(row, col_map.get('source_col_idx')) or unit.id
                unit.target = self._get_cell(row, col_map.get('target_col_idx'))
                unit.context = self._get_cell(row, col_map.get('key_col_idx'))
                
                notes = self._get_cell(row, col_map.get('comment_col_idx'))
                if notes:
                    unit.add_note(notes)

                if unit.target:
                    unit.status = TranslationStatus.TRANSLATED
                else:
                    unit.status = TranslationStatus.NEW
                
                # Preserve original row and metadata for saving
                unit.attributes['csv_original_row'] = row
                unit.attributes['csv_dialect'] = {
                    'delimiter': dialect.delimiter if hasattr(dialect, 'delimiter') else ',',
                    'quotechar': dialect.quotechar if hasattr(dialect, 'quotechar') else '"',
                    'quoting': dialect.quoting if hasattr(dialect, 'quoting') else csv.QUOTE_MINIMAL
                }
                unit.attributes['csv_headers'] = headers
                unit.attributes['csv_col_map'] = col_map
                
                units.append(unit)

        except (PermissionError, IOError, Exception) as e:
            raise FormatHandlerError(f"Failed to load CSV file {file_path}: {e}") from e

        return units

    def save(self, units: List[TranslationUnit], file_path: Path, **options) -> None:
        """Save TranslationUnits back to a CSV file, preserving structure."""
        if not units:
            return
        file_path = Path(file_path) # Ensure it's a Path object

        first_unit_attrs = units[0].attributes
        dialect_info = first_unit_attrs.get('csv_dialect', {'delimiter': ',', 'quotechar': '"', 'quoting': csv.QUOTE_MINIMAL})
        headers = first_unit_attrs.get('csv_headers')
        col_map = first_unit_attrs.get('csv_col_map')
        
        encoding = options.get('encoding', 'utf-8')

        try:
            with file_path.open('w', encoding=encoding, newline='') as f:
                writer = csv.writer(f, **dialect_info)

                if headers:
                    writer.writerow(headers)

                for unit in units:
                    row = list(unit.attributes.get('csv_original_row', []))
                    
                    # Ensure row is long enough
                    max_idx = max(col_map.values())
                    if len(row) <= max_idx:
                        row.extend([''] * (max_idx - len(row) + 1))

                    # Update row with new data
                    if col_map.get('target_col_idx') is not None:
                        row[col_map['target_col_idx']] = unit.target
                    if col_map.get('source_col_idx') is not None:
                        row[col_map['source_col_idx']] = unit.source
                    if col_map.get('key_col_idx') is not None:
                        row[col_map['key_col_idx']] = unit.context
                    if col_map.get('comment_col_idx') is not None and unit.notes:
                        row[col_map['comment_col_idx']] = unit.notes[0].text
                        
                    writer.writerow(row)
        except Exception as e:
            raise IOError(f"Failed to save CSV file {file_path}: {e}")

    def validate(self, units: List[TranslationUnit]) -> ValidationResult:
        """Validate translation units for the CSV format."""
        result = super().validate(units)
        
        if not units:
            return result

        first_unit_attrs = units[0].attributes
        headers = first_unit_attrs.get('csv_headers')
        
        if headers:
            header_count = len(headers)
            for i, unit in enumerate(units):
                row = unit.attributes.get('csv_original_row', [])
                if len(row) != header_count:
                    result.add_warning(f"Row {i+1}: Found {len(row)} columns, but there are {header_count} headers.")
        
        return result

    def _map_columns(self, headers: List[str], first_row: List[str]) -> Dict[str, int]:
        """Intelligently map CSV columns to translation unit fields."""
        col_map = {}
        
        key_candidates = ['key', 'id', 'context', 'identifier']
        source_candidates = ['source', 'original', 'en', 'english', 'source_text']
        target_candidates = ['target', 'translation', 'translated']
        comment_candidates = ['comment', 'notes', 'description', 'comments']
        
        if headers:
            # Map by header name
            for i, header in enumerate(headers):
                h_lower = header.lower()
                if not col_map.get('key_col_idx') and any(cand in h_lower for cand in key_candidates):
                    col_map['key_col_idx'] = i
                elif not col_map.get('source_col_idx') and any(cand in h_lower for cand in source_candidates):
                    col_map['source_col_idx'] = i
                elif not col_map.get('target_col_idx') and any(cand in h_lower for cand in target_candidates):
                    col_map['target_col_idx'] = i
                elif not col_map.get('comment_col_idx') and any(cand in h_lower for cand in comment_candidates):
                    col_map['comment_col_idx'] = i
            
            # Fallback for simple two/three column with headers
            if 'source_col_idx' not in col_map and len(headers) >= 2:
                col_map['key_col_idx'] = 0
                col_map['source_col_idx'] = 0
                col_map['target_col_idx'] = 1
            if 'target_col_idx' not in col_map and len(headers) >= 3:
                 col_map['target_col_idx'] = 2

        else:
            # Map by column index for headerless files
            num_cols = len(first_row)
            if num_cols >= 1:
                col_map['key_col_idx'] = 0
                col_map['source_col_idx'] = 0 # Assume key is the source
            if num_cols >= 2:
                col_map['target_col_idx'] = 1
            if num_cols >= 3:
                # Re-evaluate for 3-column (key, source, target)
                col_map['source_col_idx'] = 1
                col_map['target_col_idx'] = 2
            if num_cols >= 4:
                col_map['comment_col_idx'] = 3
                
        # If source is not found, it's the same as the key
        if 'source_col_idx' not in col_map and 'key_col_idx' in col_map:
            col_map['source_col_idx'] = col_map['key_col_idx']

        return col_map

    def _get_cell(self, row: List[str], index: Optional[int]) -> str:
        """Safely get a cell value from a row."""
        if index is not None and 0 <= index < len(row):
            return row[index].strip()
        return ""