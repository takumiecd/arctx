# CLI

この文書は、optagent のコマンドラインインターフェース（CLI）を説明します。

optagent CLI は、ライブラリAPIをコマンドラインから使うための薄いラッパーです。
各コマンドは ``JsonlRunStore`` を通じてrunをディスクに保存します。

## 共通オプション

各サブコマンドで使える共通のオプションです。

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| ``--store-dir`` | ``.optagent/runs`` | runを保存するディレクトリ |

## ``optagent init``

新しいrunを作成します。

```bash
optagent init <requirement_id> [options]
```

### 引数

| 引数 | 必須 | 説明 |
|-----|------|------|
| ``requirement_id`` | ○ | runの目的を表す識別子 |

### オプション

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| ``--target-type`` | ``code`` | 対象のカテゴリ（例: ``code``, ``kernel``） |
| ``--target-id`` | ``requirement_id`` | 具体的な対象の識別子 |
| ``--run-id`` | 自動生成 | runの識別子（省略時は ``run_<requirement_id>_<timestamp>``） |
| ``--store-dir`` | ``.optagent/runs`` | 保存先ディレクトリ |

### 出力

成功時、生成された ``run_id`` を標準出力に1行で出力します。

```bash
$ optagent init req_kernel --target-type kernel --target-id csc_linear
run_req_kernel_20260506_082356
```

### 保存されるもの

``<store-dir>/<run_id>/`` 以下に以下のファイルが作成されます。

- ``run.json`` — runのメタデータとrequirement
- ``states.jsonl`` — observed state と predicted state
- ``execution_plans.jsonl`` — 実行可能なplan（init時は空）
- ``prediction_plans.jsonl`` — 予測用plan（init時は空）
- ``predicted_transitions.jsonl`` — 予測outcome（init時は空）
- ``observed_transitions.jsonl`` — 実行結果（init時は空）
- ``derived_records.jsonl`` — 派生メモ（init時は空）

### エラー

- ``FileExistsError`` — 同じ ``run_id`` のディレクトリが既に存在する場合

## ``optagent plan``

指定したrunのcurrent observed stateからplanを作成します。

```bash
optagent plan <run_id> [options]
```

### 引数

| 引数 | 必須 | 説明 |
|-----|------|------|
| ``run_id`` | ○ | 対象のrun識別子 |

### オプション

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| ``--planner`` | ``default`` | 使用するplannerの名前 |
| ``--max-plans`` | ``1`` | 作成するplanの最大数 |
| ``--action-type`` | ``analysis`` | planのアクション種別 |
| ``--intent`` | （自動） | planの目的の説明 |
| ``--input`` | （なし） | planへの入力パラメータ（``key=value``、複数可） |
| ``--store-dir`` | ``.optagent/runs`` | runの保存先ディレクトリ |

plan は「何をするか」の宣言です。実行結果の予測は ``PredictedTransition`` が持ち、plan 自身は持ちません。

### 出力

成功時、作成されたplanの一覧をJSON配列で標準出力に出力します。

```bash
$ optagent plan run_req_kernel_20260506_082356
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
$ optagent plan my_run \
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

- ``KeyError`` — 指定した ``run_id`` が存在しない場合

## ``optagent predict``

指定したplanから予測outcome（PredictedTransition）を作成します。

```bash
optagent predict <run_id> <plan_id> [options]
```

### 引数

| 引数 | 必須 | 説明 |
|-----|------|------|
| ``run_id`` | ○ | 対象のrun識別子 |
| ``plan_id`` | ○ | 予測するplanの識別子 |

### オプション

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| ``--predictor`` | ``default`` | 使用するpredictorの名前 |
| ``--max-outcomes`` | ``1`` | 作成する予測outcomeの最大数 |
| ``--store-dir`` | ``.optagent/runs`` | runの保存先ディレクトリ |

### 出力

成功時、作成された予測outcomeの一覧をJSON配列で標準出力に出力します。

```bash
$ optagent predict run_req_kernel_20260506_082356 p_exec_0001 --max-outcomes 2
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

- ``KeyError`` — 指定した ``run_id`` または ``plan_id`` が存在しない場合

## ``optagent observe``

planの実行結果を記録します。予測と対応づけず、事実だけを保存します。

```bash
optagent observe <run_id> <plan_id> --result-id <result_id> [options]
```

### 引数

| 引数 | 必須 | 説明 |
|-----|------|------|
| ``run_id`` | ○ | 対象のrun識別子 |
| ``plan_id`` | ○ | 実行したplanの識別子 |

### オプション

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| ``--result-id`` | （必須） | 結果の識別子 |
| ``--status`` | ``completed`` | 実行ステータス |
| ``--artifact`` | （なし） | アーティファクトパス（複数可） |
| ``--raw-output`` | （なし） | 生出力パス（複数可） |
| ``--log`` | （なし） | ログパス（複数可） |
| ``--metric`` | （なし） | メトリクス（``key=value``、複数可） |
| ``--error`` | （なし） | エラーメッセージ（複数可） |
| ``--store-dir`` | ``.optagent/runs`` | runの保存先ディレクトリ |

### 出力

成功時、作成された ``ObservedTransition`` をJSONで標準出力に出力します。

```bash
$ optagent observe run_001 p_exec_0001 --result-id r_0001 --status completed \
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

- ``KeyError`` — 指定した ``run_id`` または ``plan_id`` が存在しない場合

## ``optagent promote``

予測outcome（PredictedTransition）と実測結果を対応づけ、``TraceDAG`` に記録します。

```bash
optagent promote <run_id> \
    --predicted-transition-id <predicted_id> \
    --result-id <result_id> [options]
```

### 引数

| 引数 | 必須 | 説明 |
|-----|------|------|
| ``run_id`` | ○ | 対象のrun識別子 |

### オプション

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| ``--predicted-transition-id`` | （必須） | 対応づける予測outcomeの識別子 |
| ``--result-id`` | （必須） | 結果の識別子 |
| ``--status`` | ``completed`` | 実行ステータス |
| ``--execution-plan-id`` | （推論） | 実行planの識別子 |
| ``--metric`` | （なし） | メトリクス（``key=value``、複数可） |
| ``--store-dir`` | ``.optagent/runs`` | runの保存先ディレクトリ |

### 出力

成功時、作成された ``ObservedTransition`` をJSONで標準出力に出力します。

```bash
$ optagent promote run_001 \
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

- ``KeyError`` — 指定した ``run_id`` または ``predicted_transition_id`` が存在しない場合

## ``optagent trace``

現在のobserved stateから過去の実行履歴を辿ります。

```bash
optagent trace <run_id> [options]
```

### 引数

| 引数 | 必須 | 説明 |
|-----|------|------|
| ``run_id`` | ○ | 対象のrun識別子 |

### オプション

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| ``--depth`` | （制限なし） | 辿る遷移数の上限 |
| ``--store-dir`` | ``.optagent/runs`` | runの保存先ディレクトリ |

### 出力

成功時、``TraceContext`` をJSONで標準出力に出力します。

```bash
$ optagent trace run_001 --depth 3
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

- ``KeyError`` — 指定した ``run_id`` が存在しない場合

## ``optagent list``

保存済みのrun一覧を表示します。

```bash
optagent list [options]
```

### オプション

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| ``--store-dir`` | ``.optagent/runs`` | runの保存先ディレクトリ |

### 出力

成功時、runの一覧をJSON配列で標準出力に出力します。

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

storeが空の場合、空の配列 ``[]`` を出力します。

## ``optagent refresh``

現在の observed state に ``PredictionDAG`` を作り直してアンカーします。

実行結果を記録すると current observed state が進み、古い未来予測は現在の状態とズレるため、必要に応じて ``refresh`` します。

```bash
optagent refresh <run_id> [options]
```

### 引数

| 引数 | 必須 | 説明 |
|-----|------|------|
| ``run_id`` | ○ | 対象のrun識別子 |

### オプション

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| ``--store-dir`` | ``.optagent/runs`` | runの保存先ディレクトリ |

### 出力

成功時、新しい ``PredictionDAG`` をJSONで標準出力に出力します。

```bash
$ optagent refresh run_001
{
  "dag_id": "prediction_dag_0002",
  "anchor_observed_state_id": "s_obs_0001",
  "root_predicted_state_id": "s_pred_0003",
  "stale": false
}
```

### エラー

- ``KeyError`` — 指定した ``run_id`` が存在しない場合
