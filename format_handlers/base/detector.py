"""
Intelligent format detection using multiple strategies.
"""

import mimetypes
from typing import Optional, Tuple, List, Dict
from pathlib import Path
from .registry import FormatRegistry
from .format_handler import FormatHandler

# Try to import python-magic for better MIME detection
try:
    import magic
    HAS_MAGIC = True
except ImportError:
    HAS_MAGIC = False


class FormatDetector:
    """
    Intelligent format detection using multiple strategies.
    
    This detector uses various methods to identify the best format handler
    for a given file, including file extension matching, MIME type detection,
    and content analysis.
    """
    
    def __init__(self, registry: FormatRegistry):
        """
        Initialize the format detector.
        
        Args:
            registry: FormatRegistry instance to use for handler lookup
        """
        self.registry = registry
        self.magic_detector = None
        
        # Initialize python-magic if available
        if HAS_MAGIC:
            try:
                self.magic_detector = magic.Magic(mime=True)
            except Exception as e:
                print(f"Warning: Failed to initialize python-magic: {e}")
                self.magic_detector = None
    
    def detect_format(self, file_path: Path, content_sample: bytes = None) -> Tuple[Optional[FormatHandler], float]:
        """
        Detect the best format handler for a file.
        
        Args:
            file_path: Path to the file to analyze
            content_sample: Optional sample of file content (first 8KB)
        
        Returns:
            Tuple of (handler, confidence_score) where confidence is 0.0-1.0
            Returns (None, 0.0) if no suitable handler found
        """
        if not file_path.exists():
            return None, 0.0
        
        # Read content sample if not provided
        if content_sample is None:
            try:
                with open(file_path, 'rb') as f:
                    content_sample = f.read(8192)  # Read first 8KB
            except Exception as e:
                print(f"Warning: Failed to read file sample: {e}")
                content_sample = b""
        
        candidates = []
        
        # Strategy 1: File extension matching
        extension = file_path.suffix.lower()
        if extension:
            ext_handlers = self.registry.get_handlers_for_extension(extension)
            for handler in ext_handlers:
                if handler.can_handle(file_path, content_sample):
                    candidates.append((handler, 0.8))  # High confidence for extension match
        
        # Strategy 2: MIME type detection
        mime_type = self._detect_mime_type(file_path, content_sample)
        if mime_type:
            mime_handlers = self.registry.get_handlers_for_mime(mime_type)
            for handler in mime_handlers:
                if handler.can_handle(file_path, content_sample):
                    # Check if we already have this handler from extension matching
                    existing = next((c for c in candidates if c[0] == handler), None)
                    if existing:
                        # Boost confidence if both extension and MIME match
                        candidates.remove(existing)
                        candidates.append((handler, min(0.95, existing[1] + 0.15)))
                    else:
                        candidates.append((handler, 0.85))  # High confidence for MIME match
        
        # Strategy 3: Content analysis fallback
        if not candidates:
            for handler in self.registry.get_all_handlers():
                if handler.can_handle(file_path, content_sample):
                    candidates.append((handler, 0.6))  # Lower confidence for content-only match
        
        # Return best candidate
        if candidates:
            best_handler, best_confidence = max(candidates, key=lambda x: x[1])
            return best_handler, best_confidence
        
        return None, 0.0
    
    def detect_multiple_formats(self, file_path: Path) -> List[Tuple[FormatHandler, float]]:
        """
        Get all possible format handlers ranked by confidence.
        
        Args:
            file_path: Path to the file to analyze
        
        Returns:
            List of (handler, confidence) tuples sorted by confidence (highest first)
        """
        if not file_path.exists():
            return []
        
        try:
            with open(file_path, 'rb') as f:
                content_sample = f.read(8192)
        except Exception:
            content_sample = b""
        
        candidates = []
        extension = file_path.suffix.lower()
        mime_type = self._detect_mime_type(file_path, content_sample)
        
        # Check all handlers
        for handler in self.registry.get_all_handlers():
            if handler.can_handle(file_path, content_sample):
                confidence = 0.5  # Base confidence
                
                # Boost confidence based on matches
                if extension and extension in [ext.lower() for ext in handler.file_extensions]:
                    confidence += 0.3
                
                if mime_type and mime_type in handler.mime_types:
                    confidence += 0.4
                
                # Consider file size and complexity
                try:
                    file_size = file_path.stat().st_size
                    complexity = handler.estimate_complexity(file_path)
                    
                    # Slightly prefer handlers that are better suited for file size
                    if file_size < 1024 and complexity <= 2:  # Small files, simple handlers
                        confidence += 0.05
                    elif file_size > 1048576 and complexity >= 3:  # Large files, complex handlers
                        confidence += 0.05
                except:
                    pass
                
                candidates.append((handler, min(confidence, 1.0)))
        
        # Sort by confidence (highest first)
        return sorted(candidates, key=lambda x: x[1], reverse=True)
    
    def _detect_mime_type(self, file_path: Path, content_sample: bytes) -> Optional[str]:
        """
        Detect MIME type using available methods.
        
        Args:
            file_path: Path to the file
            content_sample: Sample of file content
        
        Returns:
            MIME type string or None if detection fails
        """
        mime_type = None
        
        # Method 1: Use python-magic if available
        if self.magic_detector and content_sample:
            try:
                mime_type = self.magic_detector.from_buffer(content_sample)
                if mime_type and mime_type != 'application/octet-stream':
                    return mime_type
            except Exception as e:
                print(f"Warning: python-magic detection failed: {e}")
        
        # Method 2: Use mimetypes module
        try:
            mime_type, _ = mimetypes.guess_type(str(file_path))
            if mime_type:
                return mime_type
        except Exception:
            pass
        
        # Method 3: Simple content-based detection
        if content_sample:
            mime_type = self._simple_content_detection(content_sample)
            if mime_type:
                return mime_type
        
        return None
    
    def _simple_content_detection(self, content: bytes) -> Optional[str]:
        """
        Simple content-based MIME type detection.
        
        Args:
            content: File content sample
        
        Returns:
            MIME type string or None
        """
        if not content:
            return None
        
        try:
            # Try to decode as text
            text_content = content.decode('utf-8', errors='ignore').lower()
            
            # XML-based formats
            if text_content.startswith('<?xml'):
                if 'xliff' in text_content:
                    return 'application/x-xliff+xml'
                return 'application/xml'
            
            # JSON format
            if text_content.strip().startswith(('{', '[')):
                return 'application/json'
            
            # PO format markers
            if any(marker in text_content for marker in ['msgid', 'msgstr', '# SOME DESCRIPTIVE TITLE']):
                return 'text/x-gettext-translation'
            
            # CSV format (simple heuristic)
            lines = text_content.split('\n')[:5]  # Check first 5 lines
            if len(lines) > 1:
                # Look for comma-separated values
                comma_count = sum(line.count(',') for line in lines)
                if comma_count > len(lines):  # More commas than lines
                    return 'text/csv'
            
            # Plain text
            return 'text/plain'
            
        except Exception:
            pass
        
        # Binary content
        return 'application/octet-stream'
    
    def get_detection_info(self, file_path: Path) -> Dict[str, any]:
        """
        Get detailed detection information for debugging.
        
        Args:
            file_path: Path to the file to analyze
        
        Returns:
            Dictionary with detection details
        """
        info = {
            'file_path': str(file_path),
            'exists': file_path.exists(),
            'extension': file_path.suffix.lower(),
            'mime_type': None,
            'content_sample_size': 0,
            'candidates': [],
            'best_match': None,
            'confidence': 0.0
        }
        
        if not file_path.exists():
            return info
        
        try:
            with open(file_path, 'rb') as f:
                content_sample = f.read(8192)
            info['content_sample_size'] = len(content_sample)
            
            # Detect MIME type
            info['mime_type'] = self._detect_mime_type(file_path, content_sample)
            
            # Get all candidates
            candidates = self.detect_multiple_formats(file_path)
            info['candidates'] = [
                {'handler': handler.format_name, 'confidence': conf}
                for handler, conf in candidates
            ]
            
            # Get best match
            if candidates:
                best_handler, best_conf = candidates[0]
                info['best_match'] = best_handler.format_name
                info['confidence'] = best_conf
            
        except Exception as e:
            info['error'] = str(e)
        
        return info
    
    def __str__(self):
        magic_status = "with python-magic" if self.magic_detector else "without python-magic"
        return f"FormatDetector({len(self.registry)} handlers, {magic_status})"
    
    def __repr__(self):
        return f"<FormatDetector: {len(self.registry)} handlers>"