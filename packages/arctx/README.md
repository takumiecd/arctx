# ARCTX core

Python API for ARCTX: an append-only experiment graph for hypotheses, trials,
results, and abandoned branches.

## Installation

PyPI releases are paused (2026-10-28); the existing PyPI project is being
archived. The GitHub repository remains available for source use and personal
development, with no promised release or support schedule. From the repository
root, using Python 3.10+ in a virtual environment:

```bash
python -m pip install -e ./packages/arctx
```

## Usage

```python
import arctx

handle = arctx.init(arctx.Requirement(text="Solve the problem"))
```

## Package layout

This package provides the core API, storage, and extension framework. The
`arctx` command-line tool is in the separate `arctx-cli` package.
