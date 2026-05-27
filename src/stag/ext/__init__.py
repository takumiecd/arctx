import importlib.metadata
from pathlib import Path
from typing import Iterable

from stag.ext.base import Extension, ExtensionBase, InitContext, Violation

# Built-in extensions. (name -> "module:Class")
_BUILTIN: dict[str, str] = {
    "git": "stag.ext.git:GitExtension",
}
_STANDARD_EXTENSIONS: tuple[str, ...] = ("git",)

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


def attach_extensions(handle, names: Iterable[str]):
    """Register extension schemas and verb namespaces on a handle."""
    seen: set[str] = set()
    for name in names:
        if name in seen:
            continue
        ext = load_extension(name)
        ext.register_schema()
        ext.register_verbs(handle)
        seen.add(ext.name)
    return handle


def attach_standard_extensions(handle):
    """Attach built-in extensions that ship as part of the default package API."""
    return attach_extensions(handle, _STANDARD_EXTENSIONS)


def register_standard_cli(subparsers) -> None:
    """Register CLI namespaces provided by standard extensions."""
    for name in _STANDARD_EXTENSIONS:
        ext = load_extension(name)
        ext.register_cli(subparsers)


def attach_enabled_extensions(handle, run_dir: str | Path):
    """Attach extensions recorded in a run directory's extensions.json."""
    from stag.ext.enabled import load_enabled

    return attach_extensions(handle, (item.name for item in load_enabled(run_dir)))


__all__ = [
    "Extension",
    "ExtensionBase",
    "Violation",
    "InitContext",
    "attach_enabled_extensions",
    "attach_extensions",
    "attach_standard_extensions",
    "load_extension",
    "list_available",
    "register_standard_cli",
]
