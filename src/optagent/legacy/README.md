# Legacy Code

This directory contains the previous implementation, moved out of the public
package surface so the new architecture can be rebuilt cleanly.

- `core/`: previous evidence-graph records and JSONL store
- `v1/`: previous workflow manager implementation
- `v2/`: previous experimental state/search implementation

New code should not import from this package unless it is intentionally
adapting or comparing against the old implementation.
