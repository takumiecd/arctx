# arctx-api

Python API for ARCTX (Arc + Context) — records the process of optimization and problem-solving.

## Installation

```bash
pip install arctx-api
```

## Usage

```python
import arctx as arctx

handle = arctx.init(arctx.Requirement(text="Solve the problem"))
```

## Package layout

This package provides the core API, storage, and extension framework. The `arctx` command-line tool is in the separate `arctx-cli` package.
