# CLI

The optagent CLI is a thin wrapper around the Python API. Each command persists the run to disk via `JsonlRunStore`.

## Install

Python 3.10 or later is required.

An editable install from the repo root makes the `optagent` command available.

```bash
python3 -m pip install -e .
```

To also install dev dependencies:

```bash
python3 -m pip install -e ".[dev]"
```

To try it without installing, run it as a module from the repo root.

```bash
PYTHONPATH=src python3 -m optagent.cli.main <subcommand> ...
```

After an editable install, use:

```bash
optagent <subcommand> ...
```

## Quick Start

To see concepts, internals, and the basic loop from the CLI:

```bash
optagent guide
```

```bash
optagent init req_kernel \
  --target-type kernel \
  --target-id csc_linear \
  --run-id demo

optagent plan \
  --run demo \
  --input-node n_0000 \
  --intent "run baseline benchmark"

optagent predict \
  --run demo \
  it_0001 \
  --max-outcomes 1

optagent observe \
  --run demo \
  it_0001 \
  --matched-prediction ot_0001 \
  --status completed \
  --raw-output raw/profile.txt \
  --metric latency_ms=1.5

optagent trace --run demo --from-node n_0002
optagent show --run demo
```

## Common Specifications

Default `--store-dir` is `.optagent/runs`.

Commands other than `init` / `use` resolve the run in this order:

1. `--run`
2. `OPTAGENT_RUN_ID`
3. `<store-dir>/../current.json`

Mutating commands resolve user attribution in this order:

1. `--user`
2. `OPTAGENT_USER_ID`
3. `user.id` in `<store-dir>/../config.json`
4. `"user"`

`RunGraph` is the DAG for the entire run. `GraphView` holds only a `root_node_id` and its contents are determined by read-time reachability. To read from a view, use `reachable --view`.

## Commands

### `guide`

```bash
optagent guide
```

Displays what optagent builds, the internal `RunGraph` / transition / payload structure, the basic loop, and the mapping to major commands. Useful when you want to hand a short usage guide to an LLM or human.

To display in Japanese, use `optagent guide --lang ja`.

### `init`

```bash
optagent init <requirement_id> [--target-type code] [--target-id ID] [--run-id RID] [--store-dir DIR]
```

Creates a run and seeds the `RunGraph` and `main` view. The root node is `n_0000`. On success, outputs the run id and updates the current run.

### `plan`

```bash
optagent plan --input-node n_0000 [--input-node n_0003] [--action-type analysis] [--intent TEXT] [--input k=v] [--assumption TEXT]
```

Creates an `InputTransition` from multiple input nodes and attaches a `PlanPayload`.

### `predict`

```bash
optagent predict <input_transition_id> [--max-outcomes 1]
```

Creates prediction output `OutputTransition`s in the same `RunGraph`. Each output transition has a `PredictionPayload` attached.

### `observe`

```bash
optagent observe <input_transition_id> [--matched-prediction <output_transition_id>] [--status completed] [--artifact PATH] [--raw-output PATH] [--log PATH] [--metric k=v] [--error MSG]
```

Records an execution result as an observed output `OutputTransition`. A `ResultPayload` is attached to the new output transition.

When `--matched-prediction` is specified, the prediction output id is saved to `ResultPayload.matched_prediction_output_id`.

### `note`

```bash
optagent note --node <node_id> --text TEXT [--tag TAG]
```

Attaches a lightweight memo as `NotePayload` to a node. Existing records are not modified.

### `cut`

```bash
optagent cut --input-transition <input_transition_id> [--reason TEXT]
optagent cut --output-transition <output_transition_id> [--reason TEXT]
```

Attaches a `CutPayload`. When attached to an input transition, the entire plan becomes inactive. When attached to an output transition, only that prediction/result output becomes inactive.

### `trace`

```bash
optagent trace --from-node <node_id> [--depth N] [--include-predictions]
```

Traverses past history from the node. By default, reads centered on observed outputs. Use `--include-predictions` to also include prediction outputs.

### `outcomes`

```bash
optagent outcomes <input_transition_id> [--include-payloads]
```

For a single `InputTransition`, classifies and lists prediction / observation / active observation / inactive observation output transitions. `--include-payloads` also expands the payloads of each output transition.

### `reachable`

```bash
optagent reachable --from-node <node_id> [--include-records]
optagent reachable --view <view_name> [--include-records]
```

Displays the forward-reachable active subgraph from the specified node or view's root node. `--from-node` and `--view` are mutually exclusive and one is required. `--include-records` also returns node / transition / payload instances.

### `show`

```bash
optagent show [--node ID | --input-transition ID | --output-transition ID | --payload ID]
              [--with-payloads] [--outputs]
```

Without arguments, displays the entire run. With an individual ID, looks it up from `RunGraph`'s global records.

- `--with-payloads`: displays all payloads attached to the target record simultaneously. Cannot be used with `--payload`.
- `--outputs`: additional option when `--input-transition` is specified. Lists all output transitions with their kind (prediction/result/unknown). Combined with `--with-payloads`, expands each output's payloads. Errors if used without `--input-transition`.

### `view create`

```bash
optagent view create --root-node <node_id> --name <view_name>
```

Creates a `GraphView` rooted at the specified node. View contents are determined by read-time reachability.

### `view list`

```bash
optagent view list
```

Lists the views in the run.

### `view show`

```bash
optagent view show <view_name>
```

Displays the view's `root_node_id` and metadata.

### `list` / `current` / `use`

```bash
optagent list
optagent current [--json]
optagent use <run_id>
```

Run management commands.

## Removed Commands

In the 0.1 `RunGraph` model, the following commands are removed:

```bash
optagent extend
optagent refresh
optagent promote
optagent promote-plan
optagent promote-transition
optagent state
optagent snapshot
optagent derive
```

`state` / `snapshot` are removed along with `SnapshotPayload`. `derive` is removed along with `DerivedPayload`. Prediction-observation correspondence is stored via `observe --matched-prediction ...` in `ResultPayload`.

## Storage

The new format run directory contains the following files:

```text
run.json
graph.json
views.jsonl
nodes.jsonl
input_transitions.jsonl
output_transitions.jsonl
payloads.jsonl
```

In 0.1 alpha, there is no compatibility with old storage schemas.
