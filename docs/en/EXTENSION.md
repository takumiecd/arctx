# How to Create a ARCTX Extension

ARCTX can be extended without modifying its core codebase by defining an extension class that inherits from `ExtensionBase` and using Python's `entry_points` for packaging.

## 1. Creating the Extension Class

First, create an extension class by inheriting from `arctx.ext.base.ExtensionBase`.

```python
# my_arctx_ext/extension.py
from arctx.ext.base import ExtensionBase, InitContext
from arctx.core.run.handle import RunHandle

class MyExtension(ExtensionBase):
    name = "myext"
    version = "0.1.0"

    def register_schema(self) -> None:
        # Register custom schemas like Payloads or WorkEvents
        pass

    def register_verbs(self, handle: RunHandle) -> None:
        # Add functionality to the Python API (e.g., handle.myext.do_something())
        pass

    def register_cli(self, subparsers) -> None:
        # Register CLI subcommands (e.g., arctx myext do-something)
        pass

    def default_aliases(self) -> dict[str, str]:
        # Default CLI aliases (e.g., arctx do -> arctx myext do-something)
        return {"do": "myext do-something"}

    def on_init(self, ctx: InitContext) -> None:
        # Initialization logic triggered during `arctx init --extension myext`
        pass
```

## 2. Registering the Extension Externally (entry_points)

To allow ARCTX to automatically recognize your custom extension, use Python's standard `entry_points`.
In your package management configuration (e.g., `pyproject.toml`), register your class under the `arctx.extensions` group.

### Example `pyproject.toml`

```toml
[project]
name = "my-arctx-ext"
version = "0.1.0"
dependencies = [
    "arctx>=0.1",
]

# Register the extension with ARCTX
[project.entry-points."arctx.extensions"]
myext = "my_arctx_ext.extension:MyExtension"
```

*Note: The key on the left (`myext`) is the extension name, and the value on the right (`my_arctx_ext.extension:MyExtension`) is the module and class name to load.*

### Installation and Verification

By simply installing this package into the same Python environment as ARCTX (e.g., via `pip install .`), ARCTX will automatically recognize it.

```bash
# Check the list of recognized extensions
arctx ext list

# Enable the extension in a new run
arctx init req_demo --extension myext
```

## 3. Enabling an Extension in an Existing Run

It is also possible to enable an extension after a run has been created. Simply edit the `extensions.json` file located in the existing run directory (`<ARCTX_HOME>/runs/<uuid>/`).

```json
{
  "enabled": [
    {"name": "myext", "version": "0.1.0"}
  ]
}
```
