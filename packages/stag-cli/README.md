# stag-cli

Command-line interface and TUI for STAG (State Transition Artifact Graph).

## Installation

```bash
pip install stag-cli
```

This also installs `stag-api` as a dependency.

## Usage

```bash
stag init
stag transition create --from <node_id> --payload-type <type>
stag dump
```

## Package layout

This package provides the `stag` CLI command and TUI. The core API is in the separate `stag-api` package.
