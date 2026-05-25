# CLI

基本フロー:

```bash
stag init req_demo --run-id demo
stag plan --run demo --input-node <node_id> --intent "try baseline"
stag predict --run demo <transition_id> --max-outcomes 2
stag observe --run demo <transition_id> --status completed --metric score=1.0
stag show --run demo --transition <transition_id> --with-payloads --outputs
stag dump --run demo --fmt mermaid
```

- `stag plan`: Transition と incoming node edge と PlanPayload を append。
- `stag predict`: predicted output node と PredictionPayload を append。
- `stag observe`: observed output node と ResultPayload を append。
- `stag cut --node` / `stag cut --transition`: CutPayload を append。
- `stag outcomes <transition_id>`: transition の output node を見る。
- `stag git start <transition_id>`: transition の Git session を開始。
- `stag git finish <session_id>`: Result/Git payload を transition に attach。
