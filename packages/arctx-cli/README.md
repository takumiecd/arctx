# ARCTX CLI

Command-line interface for ARCTX experiment graphs. Use it to initialize runs,
record steps, attach results, cut abandoned branches, export reports, and serve
the Web GUI.

## Installation

PyPI releases are paused (2026-10-28); the existing PyPI project is being
archived. The GitHub repository remains available for source use and personal
development, with no promised release or support schedule. From the repository
root, using Python 3.10+ in a virtual environment:

```bash
python -m pip install -e ./packages/arctx -e ./packages/arctx-cli
```

Install both packages together so the CLI uses the matching local core.

## Usage

```bash
arctx init optimize --extension git --run-id demo
arctx add --from <node_id> --type experiment --field variant=A
arctx dump
```

## Package layout

This package provides the `arctx` CLI command. The core API is in the separate
`arctx` package, which also carries the web GUI served by `arctx web`.
