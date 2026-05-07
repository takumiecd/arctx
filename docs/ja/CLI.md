# CLI

この文書は、optagent のコマンドラインインターフェース（CLI）を説明します。

optagent CLI は、ライブラリAPIをコマンドラインから使うための薄いラッパーです。各コマンドは ``JsonlRunStore`` を通じて run をディスクに保存します。

## コマンド一覧

| カテゴリ | コマンド | 用途 |
|---------|----------|------|
| run 管理 | [``init``](#optagent-init) | 新しい run を作成する |
|          | [``use``](#optagent-use) | current run を切り替える |
|          | [``current``](#optagent-current) | current run を表示する |
|          | [``list``](#optagent-list) | 保存済み run 一覧を表示する |
|          | [``show``](#optagent-show) | run の詳細・特定エンティティを表示する |
| 計画と予測 | [``plan``](#optagent-plan) | observed state から ExecutionPlan を作る |
|          | [``extend``](#optagent-extend) | predicted state から PredictionPlan を作る |
|          | [``predict``](#optagent-predict) | plan に予測 outcome を付ける |
| 観測 | [``observe``](#optagent-observe) | plan の実行結果を記録する |
|     | [``promote``](#optagent-promote) | 予測と実測を対応づけて trace へ昇格する |
|     | [``derive``](#optagent-derive) | observed transition に派生レコードを付ける |
| DAG 操作 | [``rewind``](#optagent-rewind) | current observed state を祖先に巻き戻す（履歴は消さない） |
|          | [``refresh``](#optagent-refresh) | PredictionDAG を current state に再アンカーする |
|          | [``trace``](#optagent-trace) | observed の過去履歴を辿る |
| 状態 | [``state``](#optagent-state) | current state snapshot を表示・更新する |
|     | [``snapshot``](#optagent-snapshot) | snapshot を表示・trace から再構築する |

## 共通仕様

### 共通オプション

すべてのサブコマンドで使えるオプションです。

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| ``--store-dir`` | ``.optagent/runs`` | run を保存するディレクトリ |

### run_id の解決

``init`` / ``use`` を除く全コマンドは、対象とする run を以下の順序で解決します。run_id は CLI 引数では取らず、``--run`` フラグでのみ明示します。

1. ``--run <run_id>`` フラグ
2. 環境変数 ``OPTAGENT_RUN_ID``
3. current run マーカー（``<store-dir>/../current.json``）

どれにも該当しない場合は ``RuntimeError`` を返します。

current run は ``optagent init`` の成功時に自動でその run に切り替わり、``optagent use`` で明示的に変更できます。マーカーは ``--store-dir`` に対応する位置（デフォルトで ``.optagent/current.json``）に保存されます。日常的には ``init`` または ``use`` で current を立てておけば、各コマンドは ``--run`` を省略できます。

### 出力

エンティティを返すコマンドは整形された JSON を標準出力に出します。それ以外の状態確認系（``init`` / ``use`` / ``current`` / ``list``）はテキストや JSON 配列を返します。

---

## ``optagent init``

新しい run を作成し、その run を current run に設定します。

```bash
optagent init <requirement_id> [options]
```

### 引数

| 引数 | 必須 | 説明 |
|-----|------|------|
| ``requirement_id`` | ○ | run の目的を表す識別子 |

### オプション

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| ``--target-type`` | ``code`` | 対象のカテゴリ（例: ``code``, ``kernel``） |
| ``--target-id`` | ``requirement_id`` | 具体的な対象の識別子 |
| ``--run-id`` | 自動生成 | run の識別子（省略時は ``run_<requirement_id>_<timestamp>``） |
| ``--store-dir`` | ``.optagent/runs`` | 保存先ディレクトリ |

### 出力

成功時、生成された ``run_id`` を標準出力に1行で出力します。

```bash
$ optagent init req_kernel --target-type kernel --target-id csc_linear
run_req_kernel_20260506_082356
```

### 副作用

- ``<store-dir>/<run_id>/`` を新規作成。
- ``<store-dir>/../current.json`` を更新（以後 ``run_id`` を省略可）。

### 保存されるもの

``<store-dir>/<run_id>/`` 以下に以下のファイルが作成されます。

- ``run.json`` — run のメタデータと requirement
- ``states.jsonl`` — observed state と predicted state
- ``execution_plans.jsonl`` — 実行可能な plan（init 時は空）
- ``prediction_plans.jsonl`` — 予測用 plan（init 時は空）
- ``predicted_transitions.jsonl`` — 予測 outcome（init 時は空）
- ``observed_transitions.jsonl`` — 実行結果（init 時は空）
- ``derived_records.jsonl`` — 派生メモ（init 時は空）

### エラー

- ``FileExistsError`` — 同じ ``run_id`` のディレクトリが既に存在する場合

---

## ``optagent use``

current run を切り替えます。以後 ``run_id`` を省略したコマンドはこの run を対象にします。

```bash
optagent use <run_id> [options]
```

### 引数

| 引数 | 必須 | 説明 |
|-----|------|------|
| ``run_id`` | ○ | current にする run の識別子 |

### オプション

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| ``--store-dir`` | ``.optagent/runs`` | run の保存先ディレクトリ |

### 出力

成功時、設定した ``run_id`` を1行で出力します。

```bash
$ optagent use run_req_kernel_20260506_082356
run_req_kernel_20260506_082356
```

### エラー

- ``KeyError`` — 指定した ``run_id`` が ``--store-dir`` 配下に存在しない場合

---

## ``optagent current``

current run を表示します。

```bash
optagent current [options]
```

### オプション

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| ``--json`` | （オフ） | JSON 形式で出力する |
| ``--store-dir`` | ``.optagent/runs`` | run の保存先ディレクトリ |

### 出力

デフォルトでは ``run_id`` のみを1行で出力します。``--json`` を付けると ``run_id`` と ``store_dir`` を含むオブジェクトを出力します。

```bash
$ optagent current
run_req_kernel_20260506_082356

$ optagent current --json
{
  "run_id": "run_req_kernel_20260506_082356",
  "store_dir": ".optagent/runs"
}
```

### エラー

- ``RuntimeError`` — current run が未設定の場合

---

## ``optagent list``

保存済みの run 一覧を表示します。

```bash
optagent list [options]
```

### オプション

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| ``--store-dir`` | ``.optagent/runs`` | run の保存先ディレクトリ |

### 出力

成功時、run の一覧を JSON 配列で標準出力に出力します。

```bash
$ optagent list
[
  {
    "run_id": "run_a",
    "requirement_id": "req_kernel",
    "target_type": "kernel",
    "target_id": "csc_linear",
    "current_observed_state_id": "s_obs_0000"
  },
  {
    "run_id": "run_b",
    "requirement_id": "req_code",
    "target_type": "code",
    "target_id": "module_b",
    "current_observed_state_id": "s_obs_0000"
  }
]
```

store が空の場合、空の配列 ``[]`` を出力します。

---

## ``optagent show``

run の詳細、または run 内の特定エンティティを表示します。

```bash
optagent show [options]
```

### オプション

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| ``--run`` | （なし） | run 識別子（省略時は current run） |
| ``--state <state_id>`` | （なし） | 特定の state を表示 |
| ``--plan <plan_id>`` | （なし） | 特定の plan を表示 |
| ``--transition <transition_id>`` | （なし） | 特定の transition を表示 |
| ``--store-dir`` | ``.optagent/runs`` | run の保存先ディレクトリ |

``--state`` / ``--plan`` / ``--transition`` のいずれも指定しない場合、run 全体（``trace_dag`` と ``prediction_dag`` を含む）を返します。``--state`` などは TraceDAG・PredictionDAG の両方を横断検索します。

### 出力

成功時、結果を JSON で標準出力に出力します。

```bash
$ optagent show
{
  "run_id": "run_001",
  "requirement_id": "req_kernel",
  "current_observed_state_id": "s_obs_0001",
  "trace_dag": { ... },
  "prediction_dag": { ... }
}

$ optagent show --state s_obs_0001
{
  "state": {
    "state_id": "s_obs_0001",
    "state_kind": "observed",
    "snapshot": { ... },
    "snapshot_hash": "..."
  }
}
```

### エラー

- ``KeyError`` — ``run_id`` または指定した ``state_id`` / ``plan_id`` / ``transition_id`` が存在しない場合
- ``RuntimeError`` — run_id が解決できない場合

---

## ``optagent plan``

observed state から ``ExecutionPlan`` を作成します。実行可能な計画――次に現実で何をするか――を宣言するコマンドです。predicted state を起点にしたい場合は [``extend``](#optagent-extend) を使ってください。

```bash
optagent plan [options]
```

### オプション

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| ``--run`` | （なし） | run 識別子（省略時は current run） |
| ``--state-id`` | current observed | 起点 observed state の ID |
| ``--planner`` | ``default`` | 使用する planner の名前 |
| ``--max-plans`` | ``1`` | 作成する plan の最大数 |
| ``--action-type`` | ``analysis`` | plan のアクション種別 |
| ``--intent`` | （自動） | plan の目的の説明 |
| ``--input`` | （なし） | plan への入力パラメータ（``key=value``、複数可） |
| ``--store-dir`` | ``.optagent/runs`` | run の保存先ディレクトリ |

plan は「何をするか」の宣言です。実行結果の予測は ``PredictedTransition`` が持ち、plan 自身は持ちません。``--state-id`` に predicted state を指定すると ``KeyError`` になります。

### 出力

成功時、作成された plan の一覧を JSON 配列で標準出力に出力します。

```bash
$ optagent plan
[
  {
    "plan_id": "p_exec_0001",
    "plan_kind": "execution",
    "from_observed_state_id": "s_obs_0000",
    "action_type": "analysis",
    "intent": "inspect current state and propose next useful action",
    "inputs": {}
  }
]
```

### 実用的な例

```bash
$ optagent plan \
    --action-type edit \
    --intent "vectorize the inner loop" \
    --input file=src/kernel.py \
    --input line_start=42
[
  {
    "plan_id": "p_exec_0001",
    "plan_kind": "execution",
    "from_observed_state_id": "s_obs_0000",
    "action_type": "edit",
    "intent": "vectorize the inner loop",
    "inputs": {
      "file": "src/kernel.py",
      "line_start": "42"
    }
  }
]
```

### エラー

- ``KeyError`` — ``run_id`` が存在しない場合、または ``--state-id`` が observed state でない場合

---

## ``optagent extend``

predicted state から ``PredictionPlan`` を作成します。「もし予測どおりの未来になったら、その地点で次に何を考えるか」を宣言するコマンドです。observed state を起点にしたい場合は [``plan``](#optagent-plan) を使ってください。

predicted state には current の概念がない（``refresh`` で再アンカーされた直後の predicted root が既存）ので、``--state-id`` は必須です。

```bash
optagent extend --state-id <predicted_state_id> [options]
```

### オプション

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| ``--run`` | （なし） | run 識別子（省略時は current run） |
| ``--state-id`` | （必須） | 起点 predicted state の ID |
| ``--planner`` | ``default`` | 使用する planner の名前 |
| ``--max-plans`` | ``1`` | 作成する plan の最大数 |
| ``--action-type`` | ``analysis`` | plan のアクション種別 |
| ``--intent`` | （自動） | plan の目的の説明 |
| ``--input`` | （なし） | plan への入力パラメータ（``key=value``、複数可） |
| ``--store-dir`` | ``.optagent/runs`` | run の保存先ディレクトリ |

### 出力

成功時、作成された prediction plan の一覧を JSON 配列で標準出力に出力します。

```bash
$ optagent extend --state-id s_pred_0000
[
  {
    "plan_id": "p_pred_0001",
    "plan_kind": "prediction",
    "from_predicted_state_id": "s_pred_0000",
    "action_type": "analysis",
    "intent": "inspect predicted state and extend the future scenario",
    "inputs": {}
  }
]
```

### エラー

- ``KeyError`` — ``run_id`` が存在しない場合、または ``--state-id`` が predicted state でない場合

---

## ``optagent predict``

指定した plan から予測 outcome（``PredictedTransition``）を作成します。

```bash
optagent predict <plan_id> [options]
```

### 引数

| 引数 | 必須 | 説明 |
|-----|------|------|
| ``plan_id`` | ○ | 予測する plan の識別子 |

### オプション

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| ``--run`` | （なし） | run 識別子（省略時は current） |
| ``--predictor`` | ``default`` | 使用する predictor の名前 |
| ``--max-outcomes`` | ``1`` | 作成する予測 outcome の最大数 |
| ``--store-dir`` | ``.optagent/runs`` | run の保存先ディレクトリ |

### 出力

成功時、作成された予測 outcome の一覧を JSON 配列で標準出力に出力します。

```bash
$ optagent predict p_exec_0001 --max-outcomes 2
[
  {
    "transition_id": "t_pred_0001",
    "transition_kind": "predicted",
    "parent_plan_id": "p_exec_0001",
    "outcome_id": "outcome_1",
    "outcome_label": "default predicted outcome",
    "predicted_result": {
      "status": "unknown",
      "predictor": "default"
    },
    "to_predicted_state_id": "s_pred_0001"
  },
  {
    "transition_id": "t_pred_0002",
    "transition_kind": "predicted",
    "parent_plan_id": "p_exec_0001",
    "outcome_id": "outcome_2",
    "outcome_label": "default predicted outcome",
    "predicted_result": {
      "status": "unknown",
      "predictor": "default"
    },
    "to_predicted_state_id": "s_pred_0002"
  }
]
```

### エラー

- ``KeyError`` — ``run_id`` または ``plan_id`` が存在しない場合

---

## ``optagent observe``

plan の実行結果を記録します。予測と対応づけず、事実だけを保存します。予測と対応づける場合は ``promote`` を使います。

```bash
optagent observe <plan_id> --result-id <result_id> [options]
```

### 引数

| 引数 | 必須 | 説明 |
|-----|------|------|
| ``plan_id`` | ○ | 実行した plan の識別子 |

### オプション

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| ``--run`` | （なし） | run 識別子（省略時は current） |
| ``--result-id`` | （必須） | 結果の識別子 |
| ``--status`` | ``completed`` | 実行ステータス |
| ``--artifact`` | （なし） | アーティファクトパス（複数可） |
| ``--raw-output`` | （なし） | 生出力パス（複数可） |
| ``--log`` | （なし） | ログパス（複数可） |
| ``--metric`` | （なし） | メトリクス（``key=value``、複数可） |
| ``--error`` | （なし） | エラーメッセージ（複数可） |
| ``--store-dir`` | ``.optagent/runs`` | run の保存先ディレクトリ |

### 出力

成功時、作成された ``ObservedTransition`` を JSON で標準出力に出力します。

```bash
$ optagent observe p_exec_0001 --result-id r_0001 --status completed \
    --artifact patch.diff --metric speedup=1.15
{
  "transition_id": "t_obs_0001",
  "transition_kind": "observed",
  "execution_plan_id": "p_exec_0001",
  "action_result": {
    "result_id": "r_0001",
    "status": "completed",
    "artifacts": ["patch.diff"],
    "metrics": {"speedup": 1.15}
  }
}
```

実行後、run の ``current_observed_state_id`` が進みます。

### エラー

- ``KeyError`` — ``run_id`` または ``plan_id`` が存在しない場合

---

## ``optagent promote``

予測 outcome（``PredictedTransition``）と実測結果を対応づけ、``TraceDAG`` に記録します。

```bash
optagent promote --predicted-transition-id <predicted_id> \
    --result-id <result_id> [options]
```

### オプション

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| ``--run`` | （なし） | run 識別子（省略時は current run） |
| ``--predicted-transition-id`` | （必須） | 対応づける予測 outcome の識別子 |
| ``--result-id`` | （必須） | 結果の識別子 |
| ``--status`` | ``completed`` | 実行ステータス |
| ``--execution-plan-id`` | （推論） | 実行 plan の識別子 |
| ``--metric`` | （なし） | メトリクス（``key=value``、複数可） |
| ``--store-dir`` | ``.optagent/runs`` | run の保存先ディレクトリ |

### 出力

成功時、作成された ``ObservedTransition`` を JSON で標準出力に出力します。

```bash
$ optagent promote \
    --predicted-transition-id t_pred_0001 \
    --result-id r_0001 \
    --execution-plan-id p_exec_0001
{
  "transition_id": "t_obs_0001",
  "transition_kind": "observed",
  "execution_plan_id": "p_exec_0001",
  "matched_predicted_transition_id": "t_pred_0001",
  "action_result": {
    "result_id": "r_0001",
    "status": "completed"
  }
}
```

### エラー

- ``KeyError`` — ``run_id`` または ``predicted_transition_id`` が存在しない場合

---

## ``optagent derive``

observed transition に派生レコード（``DerivedRecord``）を付与します。実行結果から得られた所見・要約・証拠・判断などを残すために使います。

```bash
optagent derive <transition_id> [options]
```

### 引数

| 引数 | 必須 | 説明 |
|-----|------|------|
| ``transition_id`` | ○ | 対象の observed transition 識別子 |

### オプション

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| ``--run`` | （なし） | run 識別子（省略時は current） |
| ``--type`` | ``finding`` | 派生レコードの種別（``finding`` / ``summary`` / ``evidence`` / ``decision`` 等） |
| ``--id`` | 自動生成 | 明示的なレコード ID |
| ``--text`` | （なし） | 短文の本文（``payload.text`` に保存） |
| ``--confidence`` | （なし） | 信頼度（``0.0``〜``1.0``） |
| ``--store-dir`` | ``.optagent/runs`` | run の保存先ディレクトリ |

``generator`` は CLI 経由の場合 ``"cli"`` 固定です。

### 出力

成功時、作成された派生レコードを JSON で標準出力に出力します。

```bash
$ optagent derive t_obs_0001 --type finding \
    --text "speedup is bottlenecked by memory bandwidth" \
    --confidence 0.7
{
  "derived_id": "d_0001",
  "derived_type": "finding",
  "transition_id": "t_obs_0001",
  "payload": {
    "text": "speedup is bottlenecked by memory bandwidth"
  },
  "generator": "cli",
  "confidence": 0.7
}
```

### エラー

- ``KeyError`` — ``run_id`` または ``transition_id`` が存在しない場合

---

## ``optagent rewind``

current observed state を、その祖先 observed state に巻き戻します。**TraceDAG の state / transition / plan / result はひとつも消えません**。動くのはポインタ（``current_observed_state_id``）だけで、巻き戻し後の最初の ``observe`` / ``promote`` は祖先から新しい兄弟枝として枝分かれします。

`git revert` のような「履歴の打ち消し」ではなく、DAG 上の現在位置を遡るだけの操作です。別枝（兄弟）への移動は将来の `switch` / `move`（Cursor 導入時）で扱う予定で、``rewind`` は active path 上の祖先のみ受け付けます。祖先判定は depth ではなく incoming edge を辿って行います。

巻き戻し後、PredictionDAG は新しい current observed state を anchor として自動で refresh されます。

```bash
optagent rewind --to-state <observed_state_id> [options]
optagent rewind --steps <N> [options]
```

### オプション

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| ``--run`` | （なし） | run 識別子（省略時は current run） |
| ``--to-state`` | （``--steps`` と排他で必須） | 巻き戻し先の observed state ID（current の祖先） |
| ``--steps`` | （``--to-state`` と排他で必須） | current から incoming edge を遡る本数 |
| ``--reason`` | （なし） | 巻き戻し理由のメモ（将来 CursorEvent に保存予定。現状は出力にのみ含む） |
| ``--store-dir`` | ``.optagent/runs`` | run の保存先ディレクトリ |

### 出力

成功時、巻き戻し後の current observed state ノードを JSON で出力します。

```bash
$ optagent rewind --steps 1 --reason "wrong observe"
{
  "state_id": "s_obs_0000",
  "state_kind": "observed",
  "snapshot": { ... },
  "snapshot_hash": "..."
}
```

### エラー

- ``KeyError`` — ``run_id`` または ``--to-state`` が存在しない場合、``--to-state`` が observed state でない場合
- ``ValueError`` — ``--to-state`` / ``--steps`` のどちらも指定しない、または両方指定した場合、``--steps`` が非正、``--steps`` が trace の root を超える場合、``--to-state`` が current の祖先でない場合（兄弟枝など）

---

## ``optagent refresh``

current observed state に ``PredictionDAG`` を作り直してアンカーします。

実行結果を記録すると current observed state が進み、古い未来予測は現在の状態とズレるため、必要に応じて ``refresh`` します。

```bash
optagent refresh [options]
```

### オプション

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| ``--run`` | （なし） | run 識別子（省略時は current run） |
| ``--store-dir`` | ``.optagent/runs`` | run の保存先ディレクトリ |

### 出力

成功時、新しい ``PredictionDAG`` を JSON で標準出力に出力します。

```bash
$ optagent refresh
{
  "dag_id": "prediction_dag_0002",
  "anchor_observed_state_id": "s_obs_0001",
  "root_predicted_state_id": "s_pred_0003",
  "stale": false
}
```

### エラー

- ``KeyError`` — ``run_id`` が存在しない場合

---

## ``optagent trace``

current observed state から過去の実行履歴を辿ります。

```bash
optagent trace [options]
```

### オプション

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| ``--run`` | （なし） | run 識別子（省略時は current run） |
| ``--depth`` | （制限なし） | 辿る遷移数の上限 |
| ``--store-dir`` | ``.optagent/runs`` | run の保存先ディレクトリ |

### 出力

成功時、``TraceContext`` を JSON で標準出力に出力します。

```bash
$ optagent trace --depth 3
{
  "current_state_id": "s_obs_0002",
  "past_state_ids": ["s_obs_0001", "s_obs_0000"],
  "observed_transition_ids": ["t_obs_0002", "t_obs_0001"],
  "execution_plan_ids": ["p_exec_0002", "p_exec_0001"],
  "action_result_ids": ["r_0002", "r_0001"],
  "matched_predicted_transition_ids": [],
  "derived_record_ids": [],
  "artifact_refs": []
}
```

### エラー

- ``KeyError`` — ``run_id`` が存在しない場合

---

## ``optagent state``

current state snapshot を表示・更新します。``--add-*`` オプションを1つでも与えると更新モードになり、何も与えなければ参照のみです。

```bash
optagent state [options]
```

### オプション

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| ``--run`` | （なし） | run 識別子（省略時は current run） |
| ``--add-knowledge`` | （なし） | 知見の要約を追加（複数可） |
| ``--add-open-question`` | （なし） | 未解決の問いを追加（複数可） |
| ``--add-artifact`` | （なし） | アーティファクトを追加（``id:type:path``、``path`` は省略可、複数可） |
| ``--add-prediction`` | （なし） | 予測を追加（``id:summary``、複数可） |
| ``--add-branch`` | （なし） | アクティブなブランチ ID を追加（複数可） |
| ``--store-dir`` | ``.optagent/runs`` | run の保存先ディレクトリ |

### 出力

成功時、（更新後の）current observed state ノードを JSON で標準出力に出力します。

```bash
$ optagent state \
    --add-knowledge "loop is memory-bound" \
    --add-open-question "is prefetch helping?" \
    --add-artifact patch1:patch:patches/p1.diff
{
  "state_id": "s_obs_0001",
  "state_kind": "observed",
  "snapshot": {
    "knowledge": [{"finding_id": "...", "summary": "loop is memory-bound", ...}],
    "open_questions": ["is prefetch helping?"],
    "artifacts": [{"artifact_id": "patch1", "artifact_type": "patch", "path": "patches/p1.diff"}],
    ...
  },
  "snapshot_hash": "..."
}
```

### 注意

- ``--add-artifact`` の値は ``:`` 区切りで最大3要素（``id:type:path``）です。``path`` を空にする場合は末尾の ``:`` も省略できます（例: ``a1:patch``）。
- ``--add-prediction`` の値は ``id:summary`` の2要素必須です。
- ``state update`` は snapshot を再生成し、``snapshot_hash`` も再計算されます。

### エラー

- ``KeyError`` — ``run_id`` が存在しない場合
- ``ValueError`` — ``--add-artifact`` / ``--add-prediction`` の書式が不正な場合

---

## ``optagent snapshot``

current observed state の ``StateSnapshot`` を表示、または trace 履歴から再構築します。

``StateSnapshot`` は計画用のワーキングメモリで、source of truth は ``TraceDAG`` 側の ``ActionResult`` と ``DerivedRecord`` です。``--rebuild`` を付けると、対象 state までの observed transition を遡り、artifact / raw_output / log / derived_record から snapshot の ``artifacts`` と ``knowledge`` を作り直します。``snapshot_hash`` も再計算されます。

```bash
optagent snapshot [options]
```

### オプション

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| ``--run`` | （なし） | run 識別子（省略時は current run） |
| ``--state-id`` | current observed | 対象の observed state ID |
| ``--rebuild`` | （オフ） | trace 履歴から snapshot を再構築する |
| ``--store-dir`` | ``.optagent/runs`` | run の保存先ディレクトリ |

### 出力

成功時、（再構築後の）state ノードを JSON で標準出力に出力します。

```bash
$ optagent snapshot --rebuild
{
  "state_id": "s_obs_0002",
  "state_kind": "observed",
  "snapshot": {
    "artifacts": [
      {"artifact_id": "patch.diff", "artifact_type": "artifact", "path": "patch.diff"},
      {"artifact_id": "raw/run.log", "artifact_type": "raw_output", "path": "raw/run.log"}
    ],
    "knowledge": [
      {"finding_id": "d_0001", "summary": "speedup ...", "scope": "finding", ...}
    ],
    ...
  },
  "snapshot_hash": "..."
}
```

### エラー

- ``KeyError`` — ``run_id`` または ``state_id`` が存在しない、あるいは observed state でない場合
