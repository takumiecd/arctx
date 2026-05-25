# CLI

Basic flow:

```bash
stag init req_demo --run-id demo
stag plan --run demo --input-node <node_id> --intent "try baseline"
stag predict --run demo <transition_id> --max-outcomes 2
stag observe --run demo <transition_id> --status completed --metric score=1.0
stag show --run demo --transition <transition_id> --with-payloads --outputs
stag dump --run demo --fmt mermaid
```

- `stag plan`: append a Transition with incoming node edges and a PlanPayload.
- `stag predict`: append predicted output nodes and PredictionPayload records.
- `stag observe`: append an observed output node and a ResultPayload.
- `stag cut --node` / `stag cut --transition`: append a CutPayload.
- `stag outcomes <transition_id>`: list output nodes for a transition.
- `stag git start <transition_id>`: start Git tracking for a transition.
- `stag git finish <session_id>`: attach Result/Git payloads to the transition.
