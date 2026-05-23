# 状態モデル

この文書は、STAG 0.1 alpha で目指す状態モデルを説明します。

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

STAG は transition を入力側と出力側に分けます。

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

そのため、record の実体は `RunGraph` に集約します。実験 / 仮説展開は、record をコピーせず、`root_node_id` から `reachable_from` で部分集合を見ます。

同じ node は複数の view から `reachable_from` で見えうる。view の統合は通常の `plan` / `observe` で graph 上に edge を足すだけで、専用の merge 操作は無い。

## Pure Graph Records

### Node

`Node` は pure な graph node です。

```python
Node(node_id="n_<opaque>", metadata={})
```

node は状態の中身を直接持ちません。必要な情報は payload として node / input transition / output transition に attach します。

node には軽いメモとして `NotePayload` を attach できます。これは source of truth ではなく、人間や evaluator が残す文脈、観察、TODO、補足です。

### InputTransition

`InputTransition` は、複数の input node から始まる操作の入口です。

```python
InputTransition(
    input_transition_id="it_<opaque>",
    input_node_ids=("n_<opaque>", "n_<opaque>"),
)
```

`InputTransition` は graph の骨格だけを持ちます。intent、入力パラメータ、制約、仮定などの plan 情報は `PlanPayload` として attach します。

### OutputTransition

`OutputTransition` は `InputTransition` の結果として 1 つの output node に到達する edge です。

```python
OutputTransition(
    output_transition_id="ot_<opaque>",
    input_transition_id="it_<opaque>",
    to_node_id="n_<opaque>",
)
```

output の意味は attach された payload で決まります。

- `PredictionPayload`: 実行前の予測 outcome
- `ResultPayload`: 実際に起きた outcome

同一 `OutputTransition` に `PredictionPayload` と `ResultPayload` を共存させることはできません（`attach_payload` 時に拒否されます）。

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
- probability: この outcome が起きる推定確率（0〜1 / None）
- confidence: その確率推定にどれくらい自信があるか（None 可）
- predictor
- metadata

`probability` は outcome の起こりやすさ、`confidence` はその予測の信頼度で、両者は別物です。

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

`GraphView` 自体は prediction と observed を区別しません。両者は同じ `RunGraph` 上の record で、payload type で見分けます。observed のみ辿りたい場合は `run.trace`、prediction を含む outcome 一覧を見たい場合は `run.outcomes` を使います。

## Trace

`run.trace(node_id, ...)` は、指定ノードから過去の observed history を backward BFS で辿ります。

- 各ノードに incoming する OT のうち active かつ `ResultPayload` を持つものを全収集します。inactive OT（cut 済み）は辿りません。
- 各 observed OT からその `InputTransition` に移り、`input_node_ids` に列挙された**全ノード**をキューに積みます。multi-input IT（merge node）でも全祖先が正しく収集されます。
- 既訪問ノードは重複なくスキップします。
- `depth` は backward の段数（`None` で全祖先）。
- `TraceContext` のフィールド: `current_node_id`、`past_node_ids`、`output_transition_ids`、`input_transition_ids`、`result_payload_ids`、`prediction_output_transition_ids`、`note_payload_ids` は昇順 sorted tuple。`artifact_refs` は出現順を保ちつつ重複除去した tuple です。`plan_payload_ids` フィールドはありません。

## Cut

`cut` は `CutPayload` を append します。

重要な点:

- node / input transition / output transition / payload は削除しない
- active / inactive は read-time に計算する
- cut 済み input transition から新しい output は作れない
- cut 済み output transition は trace や view で inactive として扱う

### is_inactive_input_transition の判定ルール

`is_inactive_input_transition(graph, it_id)` は以下の条件のいずれかに該当する IT を inactive と判定します。

1. **直接 cut**: `CutPayload(target_kind="input_transition")` がその IT に attach されている。
2. **input_node が inactive**: IT の `input_node_ids` のいずれかが `inactive_node_ids` に含まれる（つまり、上流の OT が cut されたことで input node が inactive になった場合）。

`predict` と `observe` は inactive な IT に対して `ValueError` を送出し、新しい output transition の追加を拒否します。

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
