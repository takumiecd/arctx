from stag.ext.base import Extension, ExtensionBase, Violation, InitContext

# Built-in extensions. (name -> "module:Class")
_BUILTIN: dict[str, str] = {
    "git": "stag.ext.git:GitExtension",
}


def list_available() -> list[str]:
    """Names of registered (importable) built-in extensions."""
    return sorted(_BUILTIN.keys())


def load_extension(name: str) -> Extension:
    """Import and instantiate a registered built-in extension.

    Raises KeyError if *name* is not in the registry.
    Raises ImportError if the module/class cannot be loaded.
    """
    if name not in _BUILTIN:
        raise KeyError(f"unknown extension: {name!r}. Available: {list_available()}")
    spec = _BUILTIN[name]
    module_path, class_name = spec.split(":")
    import importlib
    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    return cls()


__all__ = [
    "Extension",
    "ExtensionBase",
    "Violation",
    "InitContext",
    "load_extension",
    "list_available",
]
