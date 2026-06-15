# Concept

arctx records work as an append-only RunGraph.

The graph skeleton is intentionally small:

- `Node`: a state or point in the work history.
- `Step`: a work step from one or more input nodes to exactly one output node.

Connectivity lives on the `Step` itself (`input_node_ids` + `output_node_id`);
there is no separate `Edge` record.

Meaning is attached with payloads. The same structural shape can represent a
plan, prediction, result, note, cut, or Git change depending on payload type.

Parallel workers append batches of nodes, steps, payloads, and work events.
Nothing is rewritten.
