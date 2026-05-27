# stag-api

Python API for STAG (State Transition Artifact Graph) — records the process of optimization and problem-solving.

## Installation

```bash
pip install stag-api
```

## Usage

```python
import stag_api as stag

handle = stag.init(stag.Requirement(text="Solve the problem"))
```

## Package layout

This package provides the core API, storage, and extension framework. The `stag` command-line tool is in the separate `stag-cli` package.
