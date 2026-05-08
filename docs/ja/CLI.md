# CLI

optagent CLI は Python API の薄いラッパーです。各 command は `JsonlRunStore` を通じて run をディスクに保存します。

実行例:

```bash
PYTHONPATH=src python3 -m optagent.cli.main <subcommand> ...
```

editable install 後は `optagent <subcommand>` でも実行できます。

## 共通仕様

`--store-dir` の既定値は `.optagent/runs` です。

`init` / `use` 以外の command は run を次の順に解決します。

1. `--run`
2. `OPTAGENT_RUN_ID`
3. `<store-dir>/../current.json`

mutating command の user attribution は次の順に解決します。

1. `--user`
2. `OPTAGENT_USER_ID`
3. `<store-dir>/../config.json` の `user.id`
4. `"user"`

`RunGraph` は run 全体の DAG です。`GraphView` はその部分集合です。通常の command は `main` view を対象にします。view を明示できる command は `--view` を受け取ります。

## Commands

### `init`

```bash
optagent init <requirement_id> [--target-type code] [--target-id ID] [--run-id RID] [--store-dir DIR]
```

run を作成し、`RunGraph` と `main` view を seed します。root node は `n_0000` です。成功時は run id を出力し、current run も更新します。

### `plan`

```bash
optagent plan --input-node n_0000 [--input-node n_0003] [--view main] [--action-type analysis] [--intent TEXT] [--input k=v] [--assumption TEXT]
```

複数 input node から `InputTransition` を作り、`PlanPayload` を attach します。

### `predict`

```bash
optagent predict <input_transition_id> [--view main] [--predictor default] [--max-outcomes 1]
```

同じ `RunGraph` に prediction output の `OutputTransition` を作ります。各 output transition には `PredictionPayload` が attach されます。

### `observe`

```bash
optagent observe <input_transition_id> [--view main] [--matched-prediction <output_transition_id>] [--status completed] [--artifact PATH] [--raw-output PATH] [--log PATH] [--metric k=v] [--error MSG]
```

実行結果を observed output の `OutputTransition` として記録します。新しい output transition に `ResultPayload` が attach されます。

`--matched-prediction` を指定すると、`ResultPayload.matched_prediction_output_id` に prediction output id を保存します。

### `note`

```bash
optagent note --node <node_id> --text TEXT [--tag TAG] [--view main]
```

node に軽いメモとして `NotePayload` を attach します。既存 record は変更しません。

### `rewind`

```bash
optagent rewind --input-transition <input_transition_id> [--view main] [--reason TEXT]
optagent rewind --output-transition <output_transition_id> [--view main] [--reason TEXT]
```

`CutPayload` を attach します。input transition に attach した場合は plan 全体を、output transition に attach した場合はその prediction / result output だけを inactive にします。

### `trace`

```bash
optagent trace --from-node <node_id> [--view main] [--depth N] [--include-predictions]
```

node から過去の履歴を辿ります。デフォルトでは observed output を中心に読みます。prediction output も含めたい場合は `--include-predictions` を使います。

### `show`

```bash
optagent show [--view main] [--node ID | --input-transition ID | --output-transition ID | --payload ID]
```

引数なしなら run 全体を表示します。出力は `graph` と `views` を含みます。個別 ID 指定時は `RunGraph` の global records から探します。

### `view create`

```bash
optagent view create --root-node <node_id> [--root-node <node_id>] --name <view_id>
```

指定 node を root とする `GraphView` を作ります。新しい view は global records をコピーしません。

### `view list`

```bash
optagent view list
```

run 内の view を一覧します。

### `view show`

```bash
optagent view show <view_id>
```

view の membership と metadata を表示します。

### `view merge`

```bash
optagent view merge <view_id> --into main [--to-node <node_id>]
```

view の選択した path を別 view の membership に追加します。record の実体は `RunGraph` にあるため、merge は copy ではありません。

### `list` / `current` / `use`

```bash
optagent list
optagent current [--json]
optagent use <run_id>
```

run 管理 command です。

## Removed Commands

0.1 の `RunGraph` モデルでは、次の command は廃止します。

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

`state` / `snapshot` は `SnapshotPayload` の削除に伴って廃止します。`derive` は `DerivedPayload` の削除に伴って廃止します。予測と実測の対応は `observe --matched-prediction ...` で `ResultPayload` に保存します。

## Storage

新形式の run directory は次のファイルを持ちます。

```text
run.json
graph.json
views.jsonl
nodes.jsonl
input_transitions.jsonl
output_transitions.jsonl
payloads.jsonl
```

0.1 alpha では旧 storage schema との互換は持ちません。
