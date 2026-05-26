import importlib.metadata

from stag.ext.base import Extension, ExtensionBase, Violation, InitContext
# Built-in extensions. (name -> "module:Class")
_BUILTIN: dict[str, str] = {
    "git": "stag.ext.git:GitExtension",
}

def _get_entry_points() -> dict[str, importlib.metadata.EntryPoint]:
    try:
        eps = importlib.metadata.entry_points(group="stag.extensions")
    except TypeError:
        # Fallback for Python 3.9
        eps = importlib.metadata.entry_points().get("stag.extensions", [])
    
    return {ep.name: ep for ep in eps}


def list_available() -> list[str]:
    """Names of registered (importable) built-in and third-party extensions."""
    names = set(_BUILTIN.keys())
    names.update(_get_entry_points().keys())
    return sorted(names)


def load_extension(name: str) -> Extension:
    """Import and instantiate a registered built-in or third-party extension.

    Raises KeyError if *name* is not in the registry.
    Raises ImportError if the module/class cannot be loaded.
    """
    if name in _BUILTIN:
        spec = _BUILTIN[name]
        module_path, class_name = spec.split(":")
        import importlib
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
        return cls()
        
    eps = _get_entry_points()
    if name in eps:
        return eps[name].load()()

    raise KeyError(f"unknown extension: {name!r}. Available: {list_available()}")


__all__ = [
    "Extension",
    "ExtensionBase",
    "Violation",
    "InitContext",
    "load_extension",
    "list_available",
]
