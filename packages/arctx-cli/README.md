# arctx-cli

Command-line interface and TUI for ARCTX (Arc + Context).

## Installation

```bash
pip install arctx-cli
```

This also installs `arctx-api` as a dependency.

## Usage

```bash
arctx init
arctx transition create --from <node_id> --payload-type <type>
arctx dump
```

## Package layout

This package provides the `arctx` CLI command and TUI. The core API is in the separate `arctx-api` package.
