"""
Universal internal representation of translation units with extensible metadata.
"""

from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional


class TranslationStatus(Enum):
    """Status of a translation unit in the workflow."""
    NEW = "new"
    TRANSLATED = "translated" 
    REVIEWED = "reviewed"
    APPROVED = "approved"
    NEEDS_WORK = "needs_work"
    FINAL = "final"


class NoteType(Enum):
    """Type of note attached to a translation unit."""
    GENERAL = "general"
    INSTRUCTION = "instruction"
    ERROR = "error"
    QUESTION = "question"
    TERMINOLOGY = "terminology"


class Note:
    """A note attached to a translation unit."""
    
    def __init__(self, text: str, author: str = "", timestamp: datetime = None):
        self.text = text
        self.author = author
        self.timestamp = timestamp or datetime.now()
        self.type: NoteType = NoteType.GENERAL
    
    def __str__(self):
        return f"[{self.type.value}] {self.text} - {self.author}"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert note to dictionary for serialization."""
        return {
            'text': self.text,
            'author': self.author,
            'timestamp': self.timestamp.isoformat(),
            'type': self.type.value
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Note':
        """Create note from dictionary."""
        note = cls(
            text=data['text'],
            author=data.get('author', ''),
            timestamp=datetime.fromisoformat(data['timestamp']) if data.get('timestamp') else None
        )
        note.type = NoteType(data.get('type', 'general'))
        return note


class TranslationUnit:
    """
    Universal internal representation of a translation unit with extensible metadata.
    
    This class serves as the central data model for all translation formats,
    providing rich metadata support for advanced features like comments, notes,
    review workflows, and approval states.
    """
    
    def __init__(self, id: str = "", source: str = "", target: str = "",
                 context: str = "", format_metadata: Optional[Dict[str, Any]] = None,
                 source_language: str = "", target_language: str = "",
                 status: TranslationStatus = TranslationStatus.NEW):
        # Core translation data
        self.id: str = id                    # Unique identifier within file
        self.source: str = source                # Source text
        self.target: str = target                # Target text
        self.source_language: str = source_language       # Source language code
        self.target_language: str = target_language       # Target language code
        
        # Status and workflow
        self.status: TranslationStatus = status
        self.reviewed: bool = False
        self.approved: bool = False
        self.locked: bool = False
        
        # Metadata and context
        self.context: str = context               # Context or comment
        self.notes: List[Note] = []          # Translator/reviewer notes
        self.max_length: Optional[int] = None # Character limit
        self.placeholders: List[str] = []    # Variables like {name}
        
        # Quality and confidence
        self.quality_score: Optional[float] = None
        self.confidence: Optional[float] = None
        self.fuzzy: bool = False
        
        # Timestamps and tracking
        self.created_at: Optional[datetime] = datetime.now() # Set creation time by default
        self.updated_at: Optional[datetime] = datetime.now() # Set update time by default
        self.translated_by: Optional[str] = None
        self.reviewed_by: Optional[str] = None
        
        # Format-specific attributes (extensible)
        self.attributes: Dict[str, Any] = {}
        
        # Original format preservation
        self.original_format: Optional[str] = None
        self.format_metadata: Dict[str, Any] = format_metadata if format_metadata is not None else {}
    
    def add_note(self, text: str, author: str = "", note_type: NoteType = NoteType.GENERAL) -> None:
        """Add a note to this translation unit."""
        note = Note(text, author)
        note.type = note_type
        self.notes.append(note)
    
    def get_notes_by_type(self, note_type: NoteType) -> List[Note]:
        """Get all notes of a specific type."""
        return [note for note in self.notes if note.type == note_type]
    
    def is_translated(self) -> bool:
        """Check if this unit has been translated."""
        return bool(self.target.strip()) and self.target != self.source
    
    def is_empty(self) -> bool:
        """Check if this unit is empty (no source text)."""
        return not self.source.strip()
    
    def mark_as_translated(self, translator: str = "") -> None:
        """Mark this unit as translated."""
        self.status = TranslationStatus.TRANSLATED
        self.updated_at = datetime.now()
        if translator:
            self.translated_by = translator
    
    def mark_as_reviewed(self, reviewer: str = "") -> None:
        """Mark this unit as reviewed."""
        self.status = TranslationStatus.REVIEWED
        self.reviewed = True
        self.updated_at = datetime.now()
        if reviewer:
            self.reviewed_by = reviewer
    
    def mark_as_approved(self) -> None:
        """Mark this unit as approved."""
        self.status = TranslationStatus.APPROVED
        self.approved = True
        self.updated_at = datetime.now()
    
    def to_legacy_format(self) -> Dict[str, str]:
        """
        Convert to legacy format for backward compatibility.
        
        Returns the traditional {"msgid": "source", "msgstr": "target", "unit_id": "id"}
        format used by the current MUTT system.
        """
        return {
            "msgid": self.source,
            "msgstr": self.target,
            "unit_id": self.id
        }
    
    @classmethod
    def from_legacy_format(cls, legacy_data: Dict[str, str]) -> 'TranslationUnit':
        """
        Create TranslationUnit from legacy format.
        
        Args:
            legacy_data: Dictionary with "msgid", "msgstr", and optionally "unit_id"
        
        Returns:
            TranslationUnit instance
        """
        unit = cls()
        unit.source = legacy_data.get("msgid", "")
        unit.target = legacy_data.get("msgstr", "")
        unit.id = legacy_data.get("unit_id", "")
        
        # Set status based on whether it's translated
        if unit.is_translated():
            unit.status = TranslationStatus.TRANSLATED
        
        return unit
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'id': self.id,
            'source': self.source,
            'target': self.target,
            'source_language': self.source_language,
            'target_language': self.target_language,
            'status': self.status.value,
            'reviewed': self.reviewed,
            'approved': self.approved,
            'locked': self.locked,
            'context': self.context,
            'notes': [note.to_dict() for note in self.notes],
            'max_length': self.max_length,
            'placeholders': self.placeholders,
            'quality_score': self.quality_score,
            'confidence': self.confidence,
            'fuzzy': self.fuzzy,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'translated_by': self.translated_by,
            'reviewed_by': self.reviewed_by,
            'attributes': self.attributes,
            'original_format': self.original_format,
            'format_metadata': self.format_metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TranslationUnit':
        """Create TranslationUnit from dictionary."""
        unit = cls()
        unit.id = data.get('id', '')
        unit.source = data.get('source', '')
        unit.target = data.get('target', '')
        unit.source_language = data.get('source_language', '')
        unit.target_language = data.get('target_language', '')
        unit.status = TranslationStatus(data.get('status', 'new'))
        unit.reviewed = data.get('reviewed', False)
        unit.approved = data.get('approved', False)
        unit.locked = data.get('locked', False)
        unit.context = data.get('context', '')
        unit.notes = [Note.from_dict(note_data) for note_data in data.get('notes', [])]
        unit.max_length = data.get('max_length')
        unit.placeholders = data.get('placeholders', [])
        unit.quality_score = data.get('quality_score')
        unit.confidence = data.get('confidence')
        unit.fuzzy = data.get('fuzzy', False)
        
        if data.get('created_at'):
            unit.created_at = datetime.fromisoformat(data['created_at'])
        if data.get('updated_at'):
            unit.updated_at = datetime.fromisoformat(data['updated_at'])
            
        unit.translated_by = data.get('translated_by')
        unit.reviewed_by = data.get('reviewed_by')
        unit.attributes = data.get('attributes', {})
        unit.original_format = data.get('original_format')
        unit.format_metadata = data.get('format_metadata', {})
        
        return unit
    
    def __str__(self):
        return f"TranslationUnit(id='{self.id}', source='{self.source[:50]}...', status={self.status.value})"
    
    def __repr__(self):
        return self.__str__()