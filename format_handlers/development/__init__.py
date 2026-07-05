try:
    from .json_handler import JSONHandler
    __all__ = ['JSONHandler']
except ImportError:
    # Handler class not yet implemented
    __all__ = []