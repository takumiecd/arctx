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

## 今後追加予定のコマンド

- ``optagent promote`` — 予測を実行結果に対応づける
- ``optagent observe`` — 予測と対応づけずに結果を記録
- ``optagent trace`` — 実行履歴を辿る
- ``optagent refresh`` — PredictionDAGを作り直す
- ``optagent list`` — 保存済みrunの一覧を表示
