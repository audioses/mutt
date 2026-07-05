"""
Dynamic registry for format handlers with plugin-style loading.
"""

import importlib
import pkgutil
from typing import Type, Dict, List, Optional
from pathlib import Path
from .format_handler import FormatHandler


class FormatRegistry:
    """
    Dynamic registry for format handlers with plugin-style loading.
    
    This registry manages all available format handlers, providing methods
    to register handlers, discover them automatically, and retrieve them
    based on file extensions or MIME types.
    """
    
    def __init__(self):
        self._handlers: Dict[str, Type[FormatHandler]] = {}
        self._handler_instances: Dict[str, FormatHandler] = {}
        self._extension_map: Dict[str, List[str]] = {}  # extension -> handler_names
        self._mime_map: Dict[str, List[str]] = {}       # mime_type -> handler_names
    
    def register(self, handler_class: Type[FormatHandler]) -> None:
        """
        Register a format handler class.
        
        Args:
            handler_class: Class that inherits from FormatHandler
        
        Raises:
            ValueError: If handler_class is not a valid FormatHandler subclass
        """
        if not issubclass(handler_class, FormatHandler):
            raise ValueError(f"{handler_class} is not a FormatHandler subclass")
        
        # Create instance to get properties
        try:
            handler = handler_class()
        except Exception as e:
            raise ValueError(f"Failed to instantiate {handler_class}: {e}")
        
        handler_name = handler.format_name.lower().replace(' ', '_')
        
        # Store both class and instance
        self._handlers[handler_name] = handler_class
        self._handler_instances[handler_name] = handler
        
        # Build lookup maps for extensions
        for ext in handler.file_extensions:
            ext_lower = ext.lower()
            if not ext_lower.startswith('.'):
                ext_lower = '.' + ext_lower
            
            if ext_lower not in self._extension_map:
                self._extension_map[ext_lower] = []
            self._extension_map[ext_lower].append(handler_name)
        
        # Build lookup maps for MIME types
        for mime_type in handler.mime_types:
            if mime_type not in self._mime_map:
                self._mime_map[mime_type] = []
            self._mime_map[mime_type].append(handler_name)
        
        print(f"Registered format handler: {handler.format_name}")
    
    def auto_discover(self, package_path: str = "format_handlers") -> int:
        """
        Automatically discover and load format handlers from a package.
        
        Args:
            package_path: Python package path to search for handlers
        
        Returns:
            Number of handlers discovered and registered
        """
        discovered_count = 0
        
        try:
            # Import the main package
            package = importlib.import_module(package_path)
            
            # Look for handler modules in subdirectories
            for subpackage_info in pkgutil.iter_modules(package.__path__):
                subpackage_name = subpackage_info.name
                
                # Skip base package, __pycache__, and compatibility module as it's not a handler package
                if subpackage_name in ['base', '__pycache__', 'compatibility']:
                    continue
                
                try:
                    # Import the subpackage
                    subpackage = importlib.import_module(f"{package_path}.{subpackage_name}")
                    
                    # Ensure it's a package before trying to iterate its path
                    if not subpackage_info.ispkg:
                        # This means it's a module, not a package. If it contains a handler,
                        # it should be handled here, but our current structure places handlers
                        # in sub-directories. For now, we skip non-package modules.
                        continue
                    
                    # Look for modules in the subpackage
                    for module_info in pkgutil.iter_modules(subpackage.__path__):
                        module_name = module_info.name
                        
                        # Skip __init__ and other special modules
                        if module_name.startswith('__'):
                            continue
                        
                        try:
                            # Import the module
                            module = importlib.import_module(f"{package_path}.{subpackage_name}.{module_name}")
                            
                            # Look for FormatHandler subclasses
                            for attr_name in dir(module):
                                attr = getattr(module, attr_name)
                                if (isinstance(attr, type) and 
                                    issubclass(attr, FormatHandler) and 
                                    attr != FormatHandler):
                                    
                                    try:
                                        self.register(attr)
                                        discovered_count += 1
                                    except Exception as e:
                                        print(f"Failed to register {attr}: {e}")
                        
                        except ImportError as e:
                            print(f"Failed to import module {package_path}.{subpackage_name}.{module_name}: {e}")
                
                except ImportError as e:
                    print(f"Failed to import subpackage {package_path}.{subpackage_name}: {e}")
        
        except ImportError as e:
            print(f"Failed to import package {package_path}: {e}")
        
        print(f"Auto-discovery completed: {discovered_count} handlers found")
        return discovered_count
    
    def get_handlers_for_extension(self, extension: str) -> List[FormatHandler]:
        """
        Get handlers that support a file extension.
        
        Args:
            extension: File extension (with or without leading dot)
        
        Returns:
            List of FormatHandler instances that support the extension
        """
        ext_lower = extension.lower()
        if not ext_lower.startswith('.'):
            ext_lower = '.' + ext_lower
        
        handler_names = self._extension_map.get(ext_lower, [])
        return [self._handler_instances[name] for name in handler_names]
    
    def get_handlers_for_mime(self, mime_type: str) -> List[FormatHandler]:
        """
        Get handlers that support a MIME type.
        
        Args:
            mime_type: MIME type string
        
        Returns:
            List of FormatHandler instances that support the MIME type
        """
        handler_names = self._mime_map.get(mime_type, [])
        return [self._handler_instances[name] for name in handler_names]
    
    def get_all_handlers(self) -> List[FormatHandler]:
        """
        Get all registered handlers.
        
        Returns:
            List of all FormatHandler instances
        """
        return list(self._handler_instances.values())
    
    def get_handler(self, name: str) -> Optional[FormatHandler]:
        """
        Get a specific handler by name.
        
        Args:
            name: Handler name (format name converted to lowercase with underscores)
        
        Returns:
            FormatHandler instance or None if not found
        """
        normalized_name = name.lower().replace(' ', '_')
        return self._handler_instances.get(normalized_name)
    
    def get_handler_by_format_name(self, format_name: str) -> Optional[FormatHandler]:
        """
        Get a handler by its format name.
        
        Args:
            format_name: Human-readable format name
        
        Returns:
            FormatHandler instance or None if not found
        """
        for handler in self._handler_instances.values():
            if handler.format_name.lower() == format_name.lower():
                return handler
        return None
    
    def list_supported_extensions(self) -> List[str]:
        """
        Get list of all supported file extensions.
        
        Returns:
            List of file extensions
        """
        return list(self._extension_map.keys())
    
    def list_supported_mime_types(self) -> List[str]:
        """
        Get list of all supported MIME types.
        
        Returns:
            List of MIME types
        """
        return list(self._mime_map.keys())
    
    def get_handler_info(self) -> Dict[str, Dict[str, any]]:
        """
        Get information about all registered handlers.
        
        Returns:
            Dictionary with handler information
        """
        info = {}
        for name, handler in self._handler_instances.items():
            info[name] = {
                'format_name': handler.format_name,
                'extensions': handler.file_extensions,
                'mime_types': handler.mime_types,
                'capabilities': handler.format_capabilities.to_dict()
            }
        return info
    
    def unregister(self, handler_name: str) -> bool:
        """
        Unregister a format handler.
        
        Args:
            handler_name: Name of the handler to unregister
        
        Returns:
            True if handler was unregistered, False if not found
        """
        normalized_name = handler_name.lower().replace(' ', '_')
        
        if normalized_name not in self._handler_instances:
            return False
        
        handler = self._handler_instances[normalized_name]
        
        # Remove from extension map
        for ext in handler.file_extensions:
            ext_lower = ext.lower()
            if not ext_lower.startswith('.'):
                ext_lower = '.' + ext_lower
            
            if ext_lower in self._extension_map:
                if normalized_name in self._extension_map[ext_lower]:
                    self._extension_map[ext_lower].remove(normalized_name)
                if not self._extension_map[ext_lower]:
                    del self._extension_map[ext_lower]
        
        # Remove from MIME map
        for mime_type in handler.mime_types:
            if mime_type in self._mime_map:
                if normalized_name in self._mime_map[mime_type]:
                    self._mime_map[mime_type].remove(normalized_name)
                if not self._mime_map[mime_type]:
                    del self._mime_map[mime_type]
        
        # Remove from main maps
        del self._handlers[normalized_name]
        del self._handler_instances[normalized_name]
        
        print(f"Unregistered format handler: {handler.format_name}")
        return True
    
    def clear(self) -> None:
        """Clear all registered handlers."""
        self._handlers.clear()
        self._handler_instances.clear()
        self._extension_map.clear()
        self._mime_map.clear()
        print("All format handlers cleared")
    
    def __len__(self) -> int:
        """Return number of registered handlers."""
        return len(self._handler_instances)
    
    def __contains__(self, handler_name: str) -> bool:
        """Check if a handler is registered."""
        normalized_name = handler_name.lower().replace(' ', '_')
        return normalized_name in self._handler_instances
    
    def __str__(self):
        return f"FormatRegistry({len(self)} handlers)"
    
    def __repr__(self):
        return f"<FormatRegistry: {len(self)} handlers>"


# Global registry instance
format_registry = FormatRegistry()