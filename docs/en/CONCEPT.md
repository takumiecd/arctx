# Concept

arctx records work as an append-only RunGraph.

The graph skeleton is intentionally small:

- `Node`: a state or point in the work history.
- `Step`: a work step from one or more nodes.
- `Edge`: connectivity only, either `node -> step` or `step -> node`.

Meaning is attached with payloads. The same structural shape can represent a
plan, prediction, result, note, cut, or Git change depending on payload type.

Parallel workers append batches of nodes, steps, edges, payloads, and
work events. Nothing is rewritten.
