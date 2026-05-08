# 状態モデル

この文書は、optagent 0.1 alpha で目指す状態モデルを説明します。

0.1 alpha では後方互換よりもモデル整理を優先します。旧 `StateNode` / `ExecutionPlan` / `PredictionPlan` / `ObservedTransition` / `PredictedTransition` / `ActionResult` 形式は廃止し、run 全体の graph record と payload に寄せます。

## 全体像

```text
RunHandle
  └── run_graph: RunGraph

RunGraph
  ├── nodes: dict[str, Node]
  ├── input_transitions: dict[str, InputTransition]
  ├── output_transitions: dict[str, OutputTransition]
  ├── payloads: dict[str, Payload]
  ├── views: dict[str, GraphView]
  ├── input_transitions_from_node
  ├── output_transitions_from_it
  ├── output_transitions_to_node
  ├── payloads_by_node
  ├── payloads_by_input_transition
  └── payloads_by_output_transition

GraphView
  ├── view_id: str
  ├── name: str
  ├── root_node_id: str   ← 単一 root node
  └── metadata
```

`RunGraph` が run 全体の DAG です。`Node` / `InputTransition` / `OutputTransition` / `Payload` の ID は run 内で global に一意です。

`GraphView` は `RunGraph` の部分集合です。`main` も特別な `GraphView` の 1 つです。

## Append-only

`RunGraph` は append-only です。一度追加した `Node` / `InputTransition` / `OutputTransition` / `Payload` は削除しません。

状態の変化、取り消し、無効化、比較、解釈の更新は、新しい record や payload を追加して表します。

- plan は `InputTransition` と `PlanPayload` を追加する
- node のメモは `NotePayload` を追加する
- 予測は `OutputTransition` と `PredictionPayload` を追加する
- 実行結果は `OutputTransition` と `ResultPayload` を追加する
- plan の無効化は `InputTransition` に `CutPayload` を追加する
- prediction / result の無効化は `OutputTransition` に `CutPayload` を追加する
- view の中身は read-time に `root_node_id` から reachability で算出する

read-time の view、active / inactive 判定、trace の表示によって「今見るべきもの」を決めます。保存済み record を破壊して過去を書き換えることはしません。

## 入力側と出力側

optagent は transition を入力側と出力側に分けます。

```text
input nodes
  -> InputTransition + PlanPayload
  -> OutputTransition + PredictionPayload | ResultPayload
  -> output node
```

入力側は複数 node を許可します。出力側は 1 つの output transition につき 1 つの node です。

```text
n_0000, n_0003
  -> it_0001
  -> ot_0001
  -> n_0004
```

この分割により、plan 情報は入力側に、prediction / result は出力側に attach できます。

## なぜ GraphView にするか

parent Dag / child Dag がそれぞれ `nodes` や `transitions` を持つと、別 Dag 間で同じ ID が使われたときに意味が壊れます。さらに、親の transition が子の node を指すような横断参照は index や storage を曖昧にします。

そのため、record の実体は `RunGraph` に集約します。実験 / 仮説展開は、record をコピーせず `GraphView` の membership で表します。

同じ node は複数の view に所属できます。merge は record のコピーではなく、選択した node / input transition / output transition / payload の ID を別 view の membership に追加する操作です。

## Pure Graph Records

### Node

`Node` は pure な graph node です。

```python
Node(node_id="n_0000", metadata={})
```

node は状態の中身を直接持ちません。必要な情報は payload として node / input transition / output transition に attach します。

node には軽いメモとして `NotePayload` を attach できます。これは source of truth ではなく、人間や evaluator が残す文脈、観察、TODO、補足です。

### InputTransition

`InputTransition` は、複数の input node から始まる操作の入口です。

```python
InputTransition(
    input_transition_id="it_0001",
    input_node_ids=("n_0000", "n_0003"),
)
```

`InputTransition` は graph の骨格だけを持ちます。intent、入力パラメータ、制約、仮定などの plan 情報は `PlanPayload` として attach します。

### OutputTransition

`OutputTransition` は `InputTransition` の結果として 1 つの output node に到達する edge です。

```python
OutputTransition(
    output_transition_id="ot_0001",
    input_transition_id="it_0001",
    to_node_id="n_0004",
)
```

output の意味は attach された payload で決まります。

- `PredictionPayload`: 実行前の予測 outcome
- `ResultPayload`: 実際に起きた outcome

1 つの `InputTransition` から prediction output も observed output も複数作れます。確率的に結果が変動する操作では同じ plan の下に複数 observed output を並べます。

## Payload

domain data は graph record に埋め込まず、payload として attach します。1 つの target に複数 payload を付けられます。

payload は `target_kind` と `target_id` を持ちます。

```python
PlanPayload(
    payload_id="pl_0001",
    target_kind="input_transition",
    target_id="it_0001",
    ...
)
```

`target_kind` は次のいずれかです。

- `node`
- `input_transition`
- `output_transition`

0.1 の最小 payload は次の通りです。

- `NotePayload`
- `PlanPayload`
- `PredictionPayload`
- `ResultPayload`
- `CutPayload`

### NotePayload

`Node` に attach される軽いメモです。

含めるもの:

- text
- author
- tags
- metadata

`NotePayload` は source of truth ではありません。状態を巨大な snapshot として保存するためではなく、node に紐づく補足や人間向けの短いメモを残すために使います。

### PlanPayload

`InputTransition` に attach される plan 情報です。

含めるもの:

- intent
- action type
- inputs
- constraints
- assumptions
- safety policy
- metadata

### PredictionPayload

prediction output に attach される予測 outcome です。

含めるもの:

- predicted artifacts
- predicted metrics
- rationale
- confidence
- predictor
- metadata

### ResultPayload

observed output に attach される実行結果です。

含めるもの:

- artifacts
- raw outputs
- logs
- metrics
- errors
- actual cost
- matched_prediction_output_id
- metadata

予測と実測の対応は `MatchPayload` ではなく、`ResultPayload.matched_prediction_output_id` で表します。

### CutPayload

`CutPayload` は `InputTransition` または `OutputTransition` に attach できます。

`InputTransition` に attach した場合、その plan 全体を inactive として扱います。その入力から出た prediction / observed output も read-time で inactive になります。

`OutputTransition` に attach した場合、その output だけを inactive として扱います。同じ input transition から出た他の output は残ります。

node 自体には `CutPayload` を attach しません。node は複数の input / output から参照されうるため、cut 対象は transition に限定します。node に付けられる payload は `NotePayload` のような非破壊の補足情報に限定します。

## GraphView

`GraphView` は `root_node_id` だけを持つラベルです。view の内容（node_ids / input_transition_ids / output_transition_ids / payload_ids）は保存せず、read-time に `RunGraph.reachable_from(root_node_id)` で算出します。

```text
main
  root_node_id: n_0000
  → reachable: n_0000, n_0001, it_0001, ot_0001, ...

exp-a
  root_node_id: n_0001
  → reachable: n_0001, n_0100, it_0100, ot_0100, ...
```

「view を統合する」場合は、main 内の任意ノードから `exp-a` の `root_node_id` への OutputTransition を 1 本足すだけです。通常の `plan` / `observe` で完結し、`view_merge` は不要です。

## Rewind

`rewind` は `CutPayload` を append します。

重要な点:

- node / input transition / output transition / payload は削除しない
- active / inactive は read-time に計算する
- cut 済み input transition から新しい output は作れない
- cut 済み output transition は trace や view で inactive として扱う

## Storage

JSONL storage は run graph 形式だけを扱います。

```text
run.json
graph.json
views.jsonl
nodes.jsonl
input_transitions.jsonl
output_transitions.jsonl
payloads.jsonl
```

storage も append-only を前提にします。論理的な取り消しや無効化は、既存行の削除ではなく追加 record / payload と read-time 計算で表します。

旧形式の migration は 0.1 alpha では持ちません。
