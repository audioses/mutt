# mutt/logic/mode_loader.py

import sys
import types
import importlib.util
from pathlib import Path
from ..modes.base_mode import BaseMode

def discover_python_modes(modes_dir="mutt/modes"):
    """
    Discover and load pre-coded Python modes from the modes directory.

    This loader ensures modules are loaded with the package context
    (mutt.modes.<modulename>) so that relative imports inside
    mode modules (e.g. `from .base_mode import BaseMode`) work correctly.

    Args:
        modes_dir (str): Path to the modes directory

    Returns:
        dict: Dictionary mapping mode names to mode classes
    """
    modes = {}
    modes_path = Path(modes_dir)

    if not modes_path.exists():
        return modes

    package_name = "mutt.modes"

    # Ensure a package module exists in sys.modules with the correct __path__
    if package_name not in sys.modules:
        package = types.ModuleType(package_name)
        package.__path__ = [str(modes_path.resolve())]
        sys.modules[package_name] = package

    # Iterate through all Python files in the modes directory
    for py_file in modes_path.glob("*.py"):
        # Skip base_mode.py and __init__.py
        if py_file.name in ["base_mode.py", "__init__.py"]:
            continue

        module_name = f"{package_name}.{py_file.stem}"
        try:
            # Create a spec with a package-qualified name so imports inside the module resolve
            spec = importlib.util.spec_from_file_location(module_name, py_file)
            module = importlib.util.module_from_spec(spec)

            # Set the package so relative imports inside the module work
            module.__package__ = package_name

            # Register the module in sys.modules before execution to support recursive imports
            sys.modules[module_name] = module

            # Execute the module
            spec.loader.exec_module(module)

            # Find classes that inherit from BaseMode
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and
                    issubclass(attr, BaseMode) and
                    attr != BaseMode):
                    # Instantiate the mode to get its name (we'll provide real context when instantiating later)
                    try:
                        mode_instance = attr(None, None)
                        modes[mode_instance.name] = attr
                    except Exception:
                        modes[attr_name] = attr
        except Exception as e:
            print(f"Error loading mode from {py_file}: {e}")

    return modes

def instantiate_mode(mode_class, app_context, aiserver):
    """
    Instantiate a mode class with the given context.

    Args:
        mode_class: The mode class to instantiate
        app_context: Application context
        aiserver: AI server instance

    Returns:
        BaseMode: Instantiated mode
    """
    return mode_class(app_context, aiserver)