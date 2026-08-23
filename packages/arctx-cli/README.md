# ARCTX CLI

Command-line interface for ARCTX experiment graphs. Use it to initialize runs,
record steps, attach results, cut abandoned branches, export reports, and serve
the Web GUI.

## Installation

```bash
pip install arctx-cli
```

This also installs `arctx` as a dependency.

## Usage

```bash
arctx init optimize --extension git --run-id demo
arctx add --from <node_id> --type experiment --field variant=A
arctx dump
```

## Package layout

This package provides the `arctx` CLI command. The core API is in the separate
`arctx` package, which also carries the web GUI served by `arctx web`.
