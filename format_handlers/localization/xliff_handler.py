"""
Handler for XLIFF 1.2 and 2.0 files.
"""

import xml.etree.ElementTree as ET
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from ..base.format_handler import FormatHandler, FormatCapabilities, ValidationResult, FormatHandlerError
from ..base.translation_unit import TranslationUnit, TranslationStatus, Note, NoteType


class XLIFFHandler(FormatHandler):
    """
    Handles reading and writing of XLIFF 1.2 and 2.0 files.

    This handler uses the standard `xml.etree.ElementTree` to parse and serialize
    XLIFF files, mapping them to the universal TranslationUnit model while preserving
    the original document structure and version.
    """

    # Namespace URIs for different XLIFF versions
    NS_MAP = {
        'xliff12': "urn:oasis:names:tc:xliff:document:1.2",
        'xliff20': "urn:oasis:names:tc:xliff:document:2.0"
    }

    @property
    def format_name(self) -> str:
        return "XLIFF"

    @property
    def file_extensions(self) -> List[str]:
        return ['.xliff', '.xlf']

    @property
    def mime_types(self) -> List[str]:
        return ['application/x-xliff+xml', 'application/xliff+xml']

    @property
    def format_capabilities(self) -> FormatCapabilities:
        """Defines the features supported by the XLIFF format."""
        caps = FormatCapabilities()
        caps.supports_comments = True
        caps.supports_context = True
        caps.supports_translation_status = True
        caps.supports_review_workflow = True
        caps.supports_file_metadata = True
        caps.supports_inline_elements = True  # Handled as raw text for now
        caps.supports_attributes = True
        caps.preserves_structure = True
        return caps

    def can_handle(self, file_path: Path, content_sample: bytes = None) -> bool:
        """
        Check if this handler can potentially process the given file based on extension.
        A more thorough check is performed during the load operation.
        """
        if file_path.suffix.lower() in self.file_extensions:
            if content_sample:
                # Simple check for XML-like structure
                try:
                    content_str = content_sample.decode('utf-8')
                    return content_str.strip().startswith('<') and '<xliff' in content_str
                except UnicodeDecodeError:
                    return False
            return True
        return False

    def load(self, file_path: Path, **options) -> List[TranslationUnit]:
        """Load an XLIFF file into a list of TranslationUnit objects."""
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
        except (ET.ParseError, PermissionError, IOError) as e:
            raise FormatHandlerError(f"Invalid XML in {file_path}: {e}") from e

        version = self._detect_version(root)
        if not version:
            raise FormatHandlerError(f"Cannot determine XLIFF version for {file_path}")

        ns = {'xliff': self.NS_MAP[version]}
        
        if version == 'xliff12':
            return self._load_v12(root, ns)
        else: # xliff20
            return self._load_v20(root, ns)

    def save(self, units: List[TranslationUnit], file_path: Path, **options) -> None:
        """Save TranslationUnits back to an XLIFF file, preserving structure."""
        if not units:
            return

        original_path = options.get('original_path', file_path)
        if not Path(original_path).exists():
             raise FormatHandlerError(f"Original file path for saving structure not found: {original_path}")
             
        try:
            tree = ET.parse(original_path)
            root = tree.getroot()
        except (ET.ParseError, PermissionError, IOError) as e:
            raise FormatHandlerError(f"Invalid XML in original file {original_path}: {e}") from e
        
        version = self._detect_version(root)
        if not version:
            raise FormatHandlerError("Cannot determine XLIFF version for saving.")

        ns_uri = self.NS_MAP[version]
        ET.register_namespace('', ns_uri)
        ns = {'xliff': ns_uri}
        
        unit_map = {unit.id: unit for unit in units}

        if version == 'xliff12':
            self._save_v12(root, ns, unit_map)
        else: # xliff20
            self._save_v20(root, ns, unit_map)

        try:
            tree.write(file_path, encoding='utf-8', xml_declaration=True)
        except Exception as e:
            raise FormatHandlerError(f"Failed to write XLIFF file to {file_path}: {e}") from e

    def _detect_version(self, root: ET.Element) -> Optional[str]:
        """Detect XLIFF version from the root element."""
        version_attr = root.get('version')
        if version_attr:
            if version_attr.startswith('1.2'):
                return 'xliff12'
            if version_attr.startswith('2.'):
                return 'xliff20'
        
        # Fallback to namespace
        if self.NS_MAP['xliff12'] in root.tag:
            return 'xliff12'
        if self.NS_MAP['xliff20'] in root.tag:
            return 'xliff20'
            
        return None

    def _get_full_text(self, element: ET.Element) -> str:
        """Extracts all text from an element, including children tags."""
        return "".join(element.itertext()).strip()

    def _set_full_text(self, element: ET.Element, text: str):
        """Sets the text of an element, clearing its previous content."""
        element.clear() # Remove children and text
        element.text = text

    def _load_v12(self, root: ET.Element, ns: Dict[str, str]) -> List[TranslationUnit]:
        """Load translation units from an XLIFF 1.2 file."""
        units = []
        for trans_unit_elem in root.findall('.//xliff:trans-unit', ns):
            unit = TranslationUnit()
            unit.id = trans_unit_elem.get('id', f"xliff12_{len(units)}")
            unit.original_format = "XLIFF 1.2"
            
            source_elem = trans_unit_elem.find('xliff:source', ns)
            target_elem = trans_unit_elem.find('xliff:target', ns)
            
            if source_elem is not None:
                unit.source = self._get_full_text(source_elem)

            if target_elem is not None:
                unit.target = self._get_full_text(target_elem)
                state = target_elem.get('state')
                if state:
                    unit.status = self._map_state_to_status(state, '1.2')
            else:
                unit.status = TranslationStatus.NEW

            # Handle notes
            note_elem = trans_unit_elem.find('xliff:note', ns)
            if note_elem is not None and note_elem.text:
                unit.add_note(note_elem.text.strip(), note_type=NoteType.GENERAL)

            # Store attributes
            unit.attributes = dict(trans_unit_elem.attrib)
            units.append(unit)
        return units

    def _load_v20(self, root: ET.Element, ns: Dict[str, str]) -> List[TranslationUnit]:
        """Load translation units from an XLIFF 2.0 file."""
        units = []
        for unit_elem in root.findall('.//xliff:unit', ns):
            unit = TranslationUnit()
            unit.id = unit_elem.get('id', f"xliff20_{len(units)}")
            unit.original_format = "XLIFF 2.0"

            segment = unit_elem.find('xliff:segment', ns)
            if segment:
                source_elem = segment.find('xliff:source', ns)
                target_elem = segment.find('xliff:target', ns)
                
                if source_elem is not None:
                    unit.source = self._get_full_text(source_elem)
                if target_elem is not None:
                    unit.target = self._get_full_text(target_elem)

                state = segment.get('state')
                if state:
                    unit.status = self._map_state_to_status(state, '2.0')
                elif unit.target:
                    unit.status = TranslationStatus.TRANSLATED
                else:
                    unit.status = TranslationStatus.NEW
            
            # Handle notes
            notes_module = unit_elem.find('xliff:notes', ns)
            if notes_module:
                for note_elem in notes_module.findall('xliff:note', ns):
                    if note_elem.text:
                        unit.add_note(note_elem.text.strip(), note_type=NoteType.GENERAL)
            
            unit.attributes = dict(unit_elem.attrib)
            units.append(unit)
        return units

    def _save_v12(self, root: ET.Element, ns: Dict[str, str], unit_map: Dict[str, TranslationUnit]):
        """Update an XLIFF 1.2 tree with translated units."""
        for trans_unit_elem in root.findall('.//xliff:trans-unit', ns):
            unit_id = trans_unit_elem.get('id')
            if unit_id in unit_map:
                unit = unit_map[unit_id]
                target_elem = trans_unit_elem.find('xliff:target', ns)
                if target_elem is None:
                    target_elem = ET.SubElement(trans_unit_elem, 'target')
                
                self._set_full_text(target_elem, unit.target)
                
                state = self._map_status_to_state(unit.status, '1.2')
                if state:
                    target_elem.set('state', state)

    def _save_v20(self, root: ET.Element, ns: Dict[str, str], unit_map: Dict[str, TranslationUnit]):
        """Update an XLIFF 2.0 tree with translated units."""
        for unit_elem in root.findall('.//xliff:unit', ns):
            unit_id = unit_elem.get('id')
            if unit_id in unit_map:
                unit = unit_map[unit_id]
                segment = unit_elem.find('xliff:segment', ns)
                if segment:
                    target_elem = segment.find('xliff:target', ns)
                    if target_elem is None:
                        target_elem = ET.SubElement(segment, 'target')
                    
                    self._set_full_text(target_elem, unit.target)
                    
                    state = self._map_status_to_state(unit.status, '2.0')
                    if state:
                        segment.set('state', state)

    def _map_state_to_status(self, state: str, version: str) -> TranslationStatus:
        """Map XLIFF state attribute to internal TranslationStatus."""
        state = state.lower()
        if version == '1.2':
            mapping = {
                'new': TranslationStatus.NEW,
                'translated': TranslationStatus.TRANSLATED,
                'needs-translation': TranslationStatus.NEW,
                'needs-review-translation': TranslationStatus.REVIEWED,
                'needs-adaptation': TranslationStatus.NEEDS_WORK,
                'signed-off': TranslationStatus.APPROVED,
                'final': TranslationStatus.FINAL,
            }
        else: # 2.0
            mapping = {
                'initial': TranslationStatus.NEW,
                'translated': TranslationStatus.TRANSLATED,
                'reviewed': TranslationStatus.REVIEWED,
                'final': TranslationStatus.FINAL,
            }
        return mapping.get(state, TranslationStatus.NEW)

    def _map_status_to_state(self, status: TranslationStatus, version: str) -> Optional[str]:
        """Map internal TranslationStatus to XLIFF state attribute."""
        if version == '1.2':
            mapping = {
                TranslationStatus.NEW: 'new',
                TranslationStatus.TRANSLATED: 'translated',
                TranslationStatus.REVIEWED: 'needs-review-translation',
                TranslationStatus.APPROVED: 'signed-off',
                TranslationStatus.NEEDS_WORK: 'needs-adaptation',
                TranslationStatus.FINAL: 'final'
            }
        else: # 2.0
            mapping = {
                TranslationStatus.NEW: 'initial',
                TranslationStatus.TRANSLATED: 'translated',
                TranslationStatus.REVIEWED: 'reviewed',
                TranslationStatus.FINAL: 'final'
            }
        return mapping.get(status)

    def validate(self, units: List[TranslationUnit]) -> ValidationResult:
        """Validate units for XLIFF compatibility."""
        result = ValidationResult(is_valid=True)
        for i, unit in enumerate(units):
            if not unit.id:
                result.add_warning(f"Unit {i} is missing an ID, which is crucial for saving back to XLIFF.")
            if not unit.source:
                 result.add_warning(f"Unit '{unit.id}' has empty source text.")
        return result