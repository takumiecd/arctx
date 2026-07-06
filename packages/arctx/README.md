# ARCTX core

Python API for ARCTX: an append-only experiment graph for hypotheses, trials,
results, and abandoned branches.

## Installation

```bash
pip install arctx
```

## Usage

```python
import arctx

handle = arctx.init(arctx.Requirement(text="Solve the problem"))
```

## Package layout

This package provides the core API, storage, and extension framework. The
`arctx` command-line tool is in the separate `arctx-cli` package.
