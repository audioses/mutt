import os
from pathlib import Path
from bs4 import BeautifulSoup
from bs4.element import Tag, NavigableString, Comment
from typing import List, Tuple, Dict, Any, Union
import hashlib

from format_handlers.base.format_handler import FormatHandler, FormatCapabilities, FormatHandlerError, ValidationResult
from format_handlers.base.translation_unit import TranslationUnit

class HTMLHandler(FormatHandler):
    format_name = "HTML"
    file_extensions = ['.html', '.htm']
    mime_types = ['text/html', 'application/xhtml+xml']
    format_capabilities = FormatCapabilities(
        supports_comments=True,
        supports_context=True,
        supports_plural_forms=False,
        supports_fuzzy_matching=False,
        supports_translation_status=True,
        supports_review_workflow=False,
        supports_inline_elements=True,
        preserves_structure=True,
        supports_attributes=True
    )

    NON_TRANSLATABLE_TAGS = ['script', 'style', 'code', 'pre', 'br', 'hr']
    TRANSLATABLE_ATTRIBUTES = {
        'img': ['alt', 'title'],
        'input': ['placeholder', 'title'],
        'textarea': ['placeholder', 'title'],
        'a': ['title'],
        'abbr': ['title'],
        'area': ['alt'],
        'link': ['title'],
        'meta': ['content']
    }
    GENERIC_TRANSLATABLE_ATTRIBUTES = ['aria-label', 'data-tooltip', 'data-label', 'data-title']

    def can_handle(self, file_path: Path, content_sample: bytes = None) -> bool:
        return file_path.suffix.lower() in self.file_extensions

    def load(self, file_path: Path, **options) -> List[TranslationUnit]:
        try:
            with open(file_path, 'rb') as f:
                raw_content = f.read()
            
            try:
                content = raw_content.decode('utf-8')
            except UnicodeDecodeError:
                content = raw_content.decode('latin-1')

            soup = BeautifulSoup(content, 'html.parser')
        except Exception as e:
            raise FormatHandlerError(f"Failed to parse HTML file {file_path}: {e}")

        units = []
        body = soup.find('body')
        if body:
            for element in body.find_all(string=True):
                if isinstance(element, Comment):
                    continue
                
                if any(p.name in self.NON_TRANSLATABLE_TAGS for p in element.parents):
                    continue
                
                text = str(element).strip()
                if text and text.strip():
                    unit = TranslationUnit()
                    unit.source = text
                    unit.context = f"Parent tag: <{element.parent.name}>"
                    unit.id = f"text_{len(units)}"
                    unit.format_metadata = {'type': 'text', 'original': str(element)}
                    units.append(unit)
        return units

    def save(self, units: List[TranslationUnit], file_path: Path, **options) -> None:
        source_path = options.get('source_path', file_path)

        if not source_path.exists():
            raise FormatHandlerError(f"Source HTML file not found for saving: {source_path}")

        try:
            with open(source_path, 'rb') as f:
                raw_content = f.read()
            
            try:
                content = raw_content.decode('utf-8')
            except UnicodeDecodeError:
                content = raw_content.decode('latin-1')

            soup = BeautifulSoup(content, 'html.parser')
        except Exception as e:
            raise FormatHandlerError(f"Failed to load source HTML file {source_path} for saving: {e}")

        text_map = {unit.source: unit.target for unit in units if unit.target}

        body = soup.find('body')
        if body:
            for element in body.find_all(string=True):
                if isinstance(element, (Comment, Tag)):
                    continue

                stripped_text = str(element).strip()
                if stripped_text in text_map:
                    element.replace_with(text_map[stripped_text])

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(str(soup.prettify()))
        except Exception as e:
            raise FormatHandlerError(f"Failed to write translated HTML to {file_path}: {e}")

    def validate(self, units: List[TranslationUnit]) -> ValidationResult:
        result = ValidationResult(is_valid=True)
        for tu in units:
            if not tu.source.strip():
                result.add_error(f"Translation unit {tu.id} has an empty source.")
        return result