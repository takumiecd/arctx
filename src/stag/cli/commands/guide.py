"""stag CLI guide command."""

from __future__ import annotations

import argparse
import sys


# ---------------------------------------------------------------------------
# Japanese topics
# ---------------------------------------------------------------------------

TOPICS_JA: dict[str, str] = {
    "overview": """\
# stag guide

stag は、最適化や問題解決の過程を append-only な履歴グラフとして記録するための基盤です。

stag は executor、code generator、benchmark runner、chatbot framework ではありません。実行や生成は外側の system が担当します。stag は、それらが何を計画し、何を予測し、実際に何を観測し、何を無効化したのかを保存します。

## stag が構築するもの

1 つの run は RunGraph です。RunGraph は状態と transition の DAG です。

- Node: 問題解決プロセス上の 1 つの地点。
- InputTransition: 1 つ以上の input node から何を試すか。
- OutputTransition: その試行から到達した 1 つの outcome node。

意味のある情報は graph record に直接埋め込まず、payload として attach します。

- PlanPayload: 何を試すつもりだったか。
- PredictionPayload: 実行前にどうなると見込んだか。
- ResultPayload: 実際に何が起きたか。
- NotePayload: node に対する軽い文脈やメモ。
- CutPayload: 間違った plan、prediction、result の append-only な無効化。

## 基本ループ

```text
init
  -> plan
  -> predict          (省略可能)
  -> stag の外で実行
  -> observe
  -> dump             (全体確認)
```

## CLI との対応

- stag init: run を作り、root node を作成する。
- stag plan: 次の試行を input transition として記録する。
- stag predict: plan に対する実行前の予測を記録する。
- stag observe: 外部実行後の実測結果を記録する。
- stag note: node に人間や evaluator 向けの文脈を残す。
- stag cut: 履歴を消さずに transition を無効化する。
- stag trace: ある node に至る履歴を読む。
- stag outcomes: 1 つの input transition の予測と実測を比較する。
- stag reachable: node や view から見える active subgraph を調べる。
- stag dump: run 全体を outline または mermaid でレンダリングする。
- stag show: run 内の record を表示する。
- stag list, current, use: 保存済み run を管理する。
- stag git: Git の変更履歴を OutputTransition の payload として記録する (詳細は `stag guide --topic git`)。

## 最小例

```bash
stag init req_kernel --target-type kernel --target-id csc_linear --run-id demo
stag plan --run demo --input-node n_0000 --intent "run baseline benchmark"
stag observe --run demo it_0001 --status completed --metric latency_ms=1.5
stag dump --run demo
```

既定では run は .stag/runs 以下に保存されます。

サブトピック一覧を確認するには `stag guide --list` を実行してください。
""",

    "agent": """\
# stag agent guide — LLM 向け利用原則

LLM が stag を使う場合の原則と anti-pattern をまとめます。

## 原則

**ドメインデータは Payload に分離する**
Node の metadata にドメインデータ (スコア、パラメータ、根拠など) を入れてはいけません。
全ての意味情報は PlanPayload / ResultPayload / NotePayload 等として attach します。

**ID は手で組み立てない**
stag が返す ID (it_XXXX, ot_XXXX, n_XXXX 等) をそのまま使います。
root node だけは n_0000 が固定です。それ以外を手で作ってはいけません。

**observed/predicted を kind フィールドで分岐しない**
OutputTransition に attach された Payload の型で判定します。
ResultPayload が付いていれば observed、PredictionPayload が付いていれば predicted です。
output_kind フィールドが "result" か "prediction" かで確認できます。

**状態確認は dump 1 発で行う**
`stag show` を何度も呼ぶよりも `stag dump` で全体を取得する方が
LLM トークン効率が良く、一貫した文脈が得られます。

**predict は省略可能**
予想が不要な場合は predict を飛ばして observe を直接呼んで構いません。

**cut は履歴を消さない**
cut は append-only の CutPayload を attach するだけです。
過去の record は削除されず、read-time に cuts.py で inactive として計算されます。

## Anti-patterns

次の古い概念・名称は 0.1 モデルには存在しません。使わないでください。

- Dag (RunGraph を使う)
- StateNode (Node を使う)
- ExecutionPlan / PredictionPlan (InputTransition + PlanPayload を使う)
- ObservedTransition / PredictedTransition (OutputTransition + Payload の型で区別)
- ActionResult (ResultPayload を使う)
- DerivedRecord / DerivedPayload (廃止)
- SnapshotPayload (廃止)

## 推奨ワークフロー

```bash
# 1. run を初期化する
stag init <requirement_id> --run-id <rid>

# 2. plan を作る
stag plan --run <rid> --input-node n_0000 --intent "..."

# 3. 外で実行し、結果を observe する
stag observe --run <rid> <it_id> --status completed --metric score=0.92

# 4. dump で全体を確認する (LLM はこれを読む)
stag dump --run <rid>

# 5. 必要なら cut して別の plan を試す
stag cut --run <rid> --input-transition <it_id> --reason "score insufficient"
```
""",

    "dump": """\
# stag dump

run 全体を 1 発でレンダリングします。LLM に文脈を渡すには outline、
図として確認するには mermaid を使います。

## コマンド書式

```bash
stag dump [--format outline|mermaid]
              [--node <node_id>]
              [--depth N]
              [--observed-only]
              [--predicted-only]
              [--full-payloads]
```

## フォーマット

- outline (デフォルト): インデント付きスパニングツリー。LLM 向けのテキスト形式。
- mermaid: flowchart TD として出力。Markdown に貼れる形で返ります。

## オプション

| オプション | 説明 |
|---|---|
| --format outline|mermaid | 出力形式 (省略時は outline) |
| --node <node_id> | 指定ノードを起点とするサブツリーだけを表示 |
| --depth N | 探索の深さ上限 |
| --observed-only | prediction output を除外し、observed (result) のみ表示 |
| --predicted-only | observed output を除外し、prediction のみ表示 |
| --full-payloads | metrics / rationale を省略せず全量表示 |

--observed-only と --predicted-only は同時指定不可です。

## outline 記号一覧

```
n_0000  [root]
└─ it_0001  [run baseline benchmark]
    └─→ n_0001  status=completed latency_ms=1.5
        └─ it_0002 (+n_0003)  [merge variant]
            └─→ n_0004  status=completed latency_ms=1.2
    └─⇢ n_0002  latency_ms=1.0
```

- → : observed OutputTransition (ResultPayload 付き)
- ⇢ : predicted OutputTransition (PredictionPayload 付き)
- ✂ : cut 済み (inactive)
- ↻n_X : すでに表示済みノードへの後方参照
- (+n_X) : multi-input IT の追加入力ノード
- ▸ feeds it_X (@n_primary) : non-primary 親ノードからの forward pointer
- joins (N): : multi-input IT が 3 個以上の場合のインデックス

## mermaid の特徴

flowchart TD 形式です。multi-input または multi-output の IT はダイアモンド中間ノード
{{...}} として展開します。observed は -->、predicted は -.-> で表現します。

## 実行例

```bash
# run 全体を outline で確認
stag dump --run demo

# mermaid で図を生成
stag dump --run demo --format mermaid

# observed のみ、深さ 3 まで
stag dump --run demo --observed-only --depth 3
```
""",

    "record": """\
# 実験 1 回を記録する典型手順

## 基本フロー (predict なし)

```bash
# 1. run を作成する (初回のみ)
stag init req_kernel --target-type kernel --target-id csc_linear --run-id demo

# 2. 何を試すかを plan として記録する
stag plan --run demo --input-node n_0000 --intent "run baseline benchmark"
# -> it_0001 が返ってくる

# 3. stag の外で実際に実行する
# (ここでベンチマーク、実験、評価などを実行)

# 4. 結果を observe として記録する
stag observe --run demo it_0001 \\
  --status completed \\
  --raw-output raw/profile.txt \\
  --metric latency_ms=1.5 \\
  --metric throughput=980
# -> ot_0001 と n_0001 が作られる

# 5. 軽いメモを残す (任意)
stag note --run demo --node n_0001 --text "baseline confirmed, latency within target"

# 6. dump で全体を確認する
stag dump --run demo
```

## predict を挟むフロー

予測を先に記録してから実行する場合は plan と observe の間に predict を入れます。

```bash
stag plan --run demo --input-node n_0001 --intent "apply loop unrolling"
# -> it_0002

stag predict --run demo it_0002 --max-outcomes 1
# -> ot_0002 (PredictionPayload 付き) が作られる

# (ここで実際に実行)

stag observe --run demo it_0002 \\
  --matched-prediction ot_0002 \\
  --status completed \\
  --metric latency_ms=1.1
# -> ot_0003 (ResultPayload 付き) が作られる
#    ResultPayload.matched_prediction_output_id = ot_0002 で紐付けられる

stag dump --run demo
```

## plan を修正したい場合

間違った plan を cut して別の plan を試します。

```bash
stag cut --run demo --input-transition it_0002 --reason "wrong approach"
stag plan --run demo --input-node n_0001 --intent "apply vectorization instead"
```
""",

    "payloads": """\
# Payload types

Payload は graph record に意味情報を attach する仕組みです。
graph record (Node / InputTransition / OutputTransition) 自体には
ドメインデータを直接埋め込みません。

## 5 種類の Payload

### NotePayload
- attach 先: Node
- 役割: 人間や evaluator 向けの軽いメモ。
- CLI: stag note --node <node_id> --text "..."

### PlanPayload
- attach 先: InputTransition
- 役割: 何を試すつもりだったかを記録する。intent、action_type、inputs、assumptions を持つ。
- CLI: stag plan で自動 attach される。

### PredictionPayload
- attach 先: OutputTransition (predicted 側)
- 役割: 実行前の予測結果。predicted_metrics、rationale を持つ。
- CLI: stag predict で作られる OutputTransition に自動 attach される。

### ResultPayload
- attach 先: OutputTransition (observed 側)
- 役割: 実際の実行結果。status、metrics、artifacts、raw_outputs を持つ。
  matched_prediction_output_id で対応する predicted OutputTransition と紐付ける。
- CLI: stag observe で作られる OutputTransition に自動 attach される。

### CutPayload
- attach 先: InputTransition または OutputTransition
- 役割: append-only な無効化マーカー。record を削除せず、read-time に inactive として扱う。
- CLI: stag cut で attach される。

## PredictionPayload と ResultPayload の排他制約

同一の OutputTransition に PredictionPayload と ResultPayload を共存させることはできません。
observed の OutputTransition には ResultPayload のみ、predicted には PredictionPayload のみが
attach されます。stag observe は常に新しい OutputTransition を作成するため、
predict で作った OutputTransition を上書きすることはありません。

## predicted と observed の識別方法

OutputTransition に付いている Payload の型で判定します。

- output_kind == "result" -> ResultPayload 付き -> observed
- output_kind == "prediction" -> PredictionPayload 付き -> predicted

Node の役割も同様で、incoming OutputTransition が全て prediction なら predicted node です。
""",

    "cut": """\
# cut — append-only な無効化

cut は履歴を削除しません。CutPayload を対象の transition に append するだけです。
active/inactive の判定は read-time に cuts.py で計算されます。

## コマンド書式

```bash
# InputTransition を cut する (plan 全体を無効化)
stag cut --run <rid> --input-transition <it_id> [--reason TEXT]

# OutputTransition を cut する (その output だけを無効化)
stag cut --run <rid> --output-transition <ot_id> [--reason TEXT]
```

## IT cut の効果

InputTransition (it_X) に CutPayload を attach すると:
- it_X が inactive になる
- it_X から出る全 OutputTransition が inactive になる
- それらの to_node と、その下流ノード全体が inactive になる

## OT cut の効果

OutputTransition (ot_X) に CutPayload を attach すると:
- ot_X が inactive になる
- ot_X の to_node が inactive になる
- to_node 以下の下流ノード全体が inactive になる

IT 全体ではなく 1 つの output だけを取り消したい場合に使います。

## 履歴は消えない

inactive になった record は物理的に削除されません。
dump や trace はデフォルトで active record のみを表示します。
is_active_node 等のユーティリティで active/inactive を確認できます。

## 実例

```bash
# 方向性が間違っていた plan 全体を無効化する
stag cut --run demo --input-transition it_0002 --reason "wrong approach"

# 1 つの observed result だけを取り消す
stag cut --run demo --output-transition ot_0003 --reason "measurement error"

# 別の plan を試す
stag plan --run demo --input-node n_0001 --intent "apply vectorization"
```
""",

    "joins": """\
# joins — multi-input transitions

plan の --input-node を複数指定すると、複数の Node を入力とする
multi-input InputTransition (join) を作れます。

## コマンド書式

```bash
stag plan --run <rid> \\
  --input-node n_0001 \\
  --input-node n_0003 \\
  --intent "merge results from two branches"
```

input_node_ids[0] (最初の --input-node) が primary parent です。

## dump outline での表示

multi-input IT は primary parent の枝に本体が表示されます。

```
n_0001  status=completed
├─ it_0005 (+n_0003)  [merge results from two branches]
│   └─→ n_0006  status=completed score=0.95
n_0003  status=completed
└─ ▸ feeds it_0005 (@n_0001)
```

- (+n_X) : 追加入力ノード (primary 以外の入力)
- ▸ feeds it_X (@n_primary) : non-primary 親ノードに付く forward pointer

## joins インデックス

multi-input IT が 3 個以上存在する場合、outline のヘッダに joins インデックスが自動表示されます。

```
run=demo  target=csc_linear  nodes=8  ...
joins (3):
  it_0004  [n_0001,n_0002]
  it_0007  [n_0003,n_0004]
  it_0010  [n_0005,n_0006]
```

## mermaid での表示

multi-input または multi-output の IT はダイアモンド中間ノード {{...}} として展開されます。
各 input Node から IT ノードへ --> が引かれ、IT ノードから to_node へ --> または -.-> が引かれます。
""",

    "git": """\
# stag git — Git 変更を OutputTransition に記録する

`stag git` は Git の commit / diff / branch を STAG の transition に対応付けます。
Git は file / commit / diff の source of truth で、STAG はその上に乗る semantic layer
として「なぜやったか / どうなると思ったか / 実際どうなったか / 何が変わったか」を記録します。

## 記録モデル

| 意味 | 保存先 |
|---|---|
| なぜやったか | InputTransition + PlanPayload |
| どうなると思ったか | OutputTransition + PredictionPayload |
| 実際どうなったか | OutputTransition + ResultPayload |
| 何が変わったか (Git) | OutputTransition + GitChangePayload |

`GitChangePayload` は OutputTransition に attach され、`ResultPayload` と共存します。
patch 本文は `<run_dir>/artifacts/git/<payload_id>.patch` に分離保存されます。

## サブコマンド

```bash
stag git start  <input_transition_id>
stag git finish <session_id> [--status completed] [--summary TEXT]
                             [--matched-prediction <ot_id>]
                             [--artifact PATH] [--metric k=v] ...
stag git finish <session_id> --output-transition <ot_id>
stag git status
stag git diff   <session_id> | --output-transition <ot_id>
stag git log    <session_id> | --output-transition <ot_id>
```

## 基本フロー

```bash
stag plan --run demo --input-node n_0000 --intent "add Git payload support"

stag git start it_0001
# -> gs_0001 (pending session)

# (ファイル編集 + git commit)

stag git finish gs_0001 --status completed --summary "added MVP"
# -> 新 OutputTransition + ResultPayload + GitChangePayload を作る (形式 A)
```

## 既存 observe に Git だけ後付けする (形式 B)

```bash
stag observe it_0001 --status completed
# -> ot_0003 (ResultPayload 付き)
stag git finish gs_0001 --output-transition ot_0003
# -> ot_0003 に GitChangePayload だけを attach
```

形式 B では `--matched-prediction` や `--status` 等の ResultPayload 変更系オプションは
受け付けません。意味は元の observe で確定済みのためです。

## 制約 (MVP)

- `start` 時に detached HEAD は error。
- `start` から `finish` までの branch 切替は error。
- `finish` 時の tracked file の dirty 状態は error。untracked は許容。
- 空 diff (base == HEAD) は warning だけで通常通り attach する。
- 同じ IT に observed OT が既にある状態で形式 A を使うと warning。`--output-transition` の利用を促す。

## 出力先

```text
<run_dir>/git/sessions/gs_0001.json     # pending session
<run_dir>/git/current.json              # 最後に start した session への pointer
<run_dir>/artifacts/git/pl_0008.patch   # GitChangePayload の patch 本文
```

詳細仕様は `docs/ja/GIT_INTEGRATION.md` を参照してください。
""",
}


# ---------------------------------------------------------------------------
# English topics
# ---------------------------------------------------------------------------

TOPICS_EN: dict[str, str] = {
    "overview": """\
# stag guide

stag records optimization and problem-solving processes as an append-only history graph.

It is not an executor, code generator, benchmark runner, or chatbot framework. Those
systems run outside stag. stag records what they planned, predicted, observed,
and invalidated.

## What stag builds

Each run is a RunGraph: a DAG of states and transitions.

- Node: a point in the process.
- InputTransition: the operation to try from one or more input nodes.
- OutputTransition: one possible outcome node reached from an input transition.

Meaning is attached with payloads instead of being embedded in graph records.

- PlanPayload: what we intended to try.
- PredictionPayload: what we expected before running it.
- ResultPayload: what actually happened.
- NotePayload: lightweight context on a node.
- CutPayload: append-only invalidation for a bad plan, prediction, or result.

## Core loop

```text
init
  -> plan
  -> predict          (optional)
  -> run outside stag
  -> observe
  -> dump             (inspect the whole run)
```

## CLI mapping

- stag init: create a run and seed the root node.
- stag plan: record the next trial as an input transition.
- stag predict: record expected outcomes for a plan.
- stag observe: record actual results after external execution.
- stag note: attach human or evaluator context to a node.
- stag cut: invalidate a transition without deleting history.
- stag trace: read the path that led to a node.
- stag outcomes: compare predictions and observations for one input transition.
- stag reachable: inspect the active subgraph from a node or view.
- stag dump: render the whole run as outline or mermaid.
- stag show: inspect run records.
- stag list, current, use: manage saved runs.
- stag git: record Git changes as a payload on the OutputTransition (see `stag guide --topic git`).

## Minimal example

```bash
stag init req_kernel --target-type kernel --target-id csc_linear --run-id demo
stag plan --run demo --input-node n_0000 --intent "run baseline benchmark"
stag observe --run demo it_0001 --status completed --metric latency_ms=1.5
stag dump --run demo
```

Runs are stored under .stag/runs by default.

Run `stag guide --list` to see all available subtopics.
""",

    "agent": """\
# stag agent guide — rules for LLM agents

## Principles

**Keep domain data in Payloads, not Node metadata.**
Scores, parameters, rationale, etc. belong in PlanPayload, ResultPayload, or NotePayload.
Node metadata is for graph-level bookkeeping only.

**Never hand-craft IDs.**
Use IDs returned by stag commands (it_XXXX, ot_XXXX, n_XXXX).
The root node is always n_0000. Do not construct any other ID manually.

**Do not branch on observed vs predicted by a kind field.**
Identify the output by the Payload type attached to the OutputTransition:
ResultPayload -> observed (output_kind == "result"),
PredictionPayload -> predicted (output_kind == "prediction").

**Use dump instead of repeated show calls.**
A single `stag dump` returns the full run context in one token-efficient block.
Multiple `stag show` calls waste tokens and give a fragmented picture.

**predict is optional.**
When you have no prior expectation, skip predict and call observe directly.

**cut does not delete history.**
cut appends a CutPayload. Past records remain; inactive status is computed at read time.

## Anti-patterns — terms that do not exist in 0.1

Do not use these names in code, comments, or tool calls:

- Dag (use RunGraph)
- StateNode (use Node)
- ExecutionPlan / PredictionPlan (use InputTransition + PlanPayload)
- ObservedTransition / PredictedTransition (use OutputTransition + Payload type)
- ActionResult (use ResultPayload)
- DerivedRecord / DerivedPayload (removed)
- SnapshotPayload (removed)

## Recommended workflow

```bash
stag init <requirement_id> --run-id <rid>
stag plan --run <rid> --input-node n_0000 --intent "..."
# run the experiment externally
stag observe --run <rid> <it_id> --status completed --metric score=0.92
stag dump --run <rid>
# if needed, invalidate and retry
stag cut --run <rid> --input-transition <it_id> --reason "score insufficient"
```
""",

    "dump": """\
# stag dump

Render the whole run in one call. Use outline for LLM context, mermaid for diagrams.

## Usage

```bash
stag dump [--format outline|mermaid]
              [--node <node_id>]
              [--depth N]
              [--observed-only]
              [--predicted-only]
              [--full-payloads]
```

## Formats

- outline (default): indented spanning tree, LLM-friendly text.
- mermaid: flowchart TD output, paste directly into Markdown.

## Options

| Option | Description |
|---|---|
| --format outline|mermaid | output format (default: outline) |
| --node <node_id> | render only the subtree rooted at this node |
| --depth N | max traversal depth |
| --observed-only | hide prediction outputs, show results only |
| --predicted-only | hide result outputs, show predictions only |
| --full-payloads | show full metrics/rationale without truncation |

--observed-only and --predicted-only are mutually exclusive.

## Outline symbols

```
n_0000  [root]
└─ it_0001  [run baseline benchmark]
    └─→ n_0001  status=completed latency_ms=1.5
        └─ it_0002 (+n_0003)  [merge variant]
            └─→ n_0004  status=completed latency_ms=1.2
    └─⇢ n_0002  latency_ms=1.0
```

- → : observed OutputTransition (ResultPayload attached)
- ⇢ : predicted OutputTransition (PredictionPayload attached)
- ✂ : cut (inactive)
- ↻n_X : back-reference to an already-rendered node
- (+n_X) : additional input node for a multi-input IT
- ▸ feeds it_X (@n_primary) : forward pointer on a non-primary parent node
- joins (N): : index shown when 3+ multi-input ITs exist

## Mermaid notes

Multi-input or multi-output ITs are rendered as diamond intermediate nodes {{...}}.
Observed edges use -->, predicted edges use -.->

## Examples

```bash
stag dump --run demo
stag dump --run demo --format mermaid
stag dump --run demo --observed-only --depth 3
```
""",

    "record": """\
# Recording one experiment

## Basic flow (no predict)

```bash
# Create the run (once)
stag init req_kernel --target-type kernel --target-id csc_linear --run-id demo

# Record what you plan to try
stag plan --run demo --input-node n_0000 --intent "run baseline benchmark"
# -> returns it_0001

# Run the experiment externally

# Record the result
stag observe --run demo it_0001 \\
  --status completed \\
  --raw-output raw/profile.txt \\
  --metric latency_ms=1.5 \\
  --metric throughput=980
# -> creates ot_0001 and n_0001

# Optionally add a note
stag note --run demo --node n_0001 --text "baseline confirmed"

# Inspect the whole run
stag dump --run demo
```

## With predict

```bash
stag plan --run demo --input-node n_0001 --intent "apply loop unrolling"
# -> it_0002

stag predict --run demo it_0002 --max-outcomes 1
# -> creates ot_0002 with PredictionPayload

# Run the experiment externally

stag observe --run demo it_0002 \\
  --matched-prediction ot_0002 \\
  --status completed \\
  --metric latency_ms=1.1
# -> creates ot_0003 with ResultPayload.matched_prediction_output_id=ot_0002

stag dump --run demo
```

## Correcting a mistake

```bash
stag cut --run demo --input-transition it_0002 --reason "wrong approach"
stag plan --run demo --input-node n_0001 --intent "apply vectorization instead"
```
""",

    "payloads": """\
# Payload types

Payloads attach meaning to graph records without embedding domain data in the records
themselves. Node, InputTransition, and OutputTransition stay structurally pure.

## Five payload types

NotePayload
  Attaches to: Node
  Purpose: lightweight human or evaluator context.
  CLI: stag note --node <node_id> --text "..."

PlanPayload
  Attaches to: InputTransition
  Purpose: records intent, action_type, inputs, assumptions.
  CLI: attached automatically by stag plan.

PredictionPayload
  Attaches to: OutputTransition (predicted side)
  Purpose: pre-execution expectation: predicted_metrics, rationale.
  CLI: attached automatically by stag predict.

ResultPayload
  Attaches to: OutputTransition (observed side)
  Purpose: actual outcome: status, metrics, artifacts, raw_outputs.
    matched_prediction_output_id links to the corresponding predicted OutputTransition.
  CLI: attached automatically by stag observe.

CutPayload
  Attaches to: InputTransition or OutputTransition
  Purpose: append-only invalidation marker. Does not delete records.
  CLI: attached by stag cut.

## PredictionPayload and ResultPayload are mutually exclusive on the same OT

stag observe always creates a new OutputTransition with a ResultPayload.
It never overwrites the OutputTransition created by stag predict.
Attaching both to the same OutputTransition is rejected by the runtime.

## Identifying observed vs predicted

Check the Payload type on the OutputTransition:
- output_kind == "result"     -> ResultPayload -> observed
- output_kind == "prediction" -> PredictionPayload -> predicted
""",

    "cut": """\
# cut — append-only invalidation

cut attaches a CutPayload to a transition. It does not delete any records.
Active/inactive status is computed at read time by cuts.py.

## Usage

```bash
# Cut an entire plan (InputTransition)
stag cut --run <rid> --input-transition <it_id> [--reason TEXT]

# Cut a single output (OutputTransition)
stag cut --run <rid> --output-transition <ot_id> [--reason TEXT]
```

## IT cut effects

Attaching CutPayload to an InputTransition marks as inactive:
- the InputTransition itself
- all OutputTransitions from it
- their to_nodes and all downstream nodes

## OT cut effects

Attaching CutPayload to an OutputTransition marks as inactive:
- that OutputTransition
- its to_node
- all nodes downstream of to_node

Use OT cut when you want to invalidate one specific output without cancelling the
whole plan.

## Records are never deleted

Inactive records remain in storage. dump and trace show active records by default.
Use is_active_node and related helpers to filter programmatically.

## Example

```bash
stag cut --run demo --input-transition it_0002 --reason "wrong approach"
stag cut --run demo --output-transition ot_0003 --reason "measurement error"
stag plan --run demo --input-node n_0001 --intent "apply vectorization"
```
""",

    "joins": """\
# joins — multi-input transitions

Pass multiple --input-node flags to plan to create a multi-input InputTransition.

## Usage

```bash
stag plan --run <rid> \\
  --input-node n_0001 \\
  --input-node n_0003 \\
  --intent "merge results from two branches"
```

input_node_ids[0] (the first --input-node) is the primary parent.

## Outline rendering

The IT appears under the primary parent's branch:

```
n_0001  status=completed
├─ it_0005 (+n_0003)  [merge results from two branches]
│   └─→ n_0006  status=completed score=0.95
n_0003  status=completed
└─ ▸ feeds it_0005 (@n_0001)
```

- (+n_X) : extra input node listed inline
- ▸ feeds it_X (@n_primary) : forward pointer on each non-primary parent

## joins index

When 3 or more multi-input ITs exist, the outline header shows a joins index:

```
run=demo  target=csc_linear  nodes=8  ...
joins (3):
  it_0004  [n_0001,n_0002]
  it_0007  [n_0003,n_0004]
  it_0010  [n_0005,n_0006]
```

## Mermaid rendering

Multi-input ITs appear as diamond intermediate nodes {{...}}.
Each input Node has an edge to the IT node, then the IT node connects to its outputs.
""",

    "git": """\
# stag git — record Git changes on an OutputTransition

`stag git` connects Git commits / diffs / branches to STAG transitions.
Git remains the source of truth for files and history; STAG adds the semantic layer
of "why we did it / what we expected / what actually happened / what changed".

## Recording model

| Meaning | Stored as |
|---|---|
| Why we did it | InputTransition + PlanPayload |
| What we expected | OutputTransition + PredictionPayload |
| What actually happened | OutputTransition + ResultPayload |
| What changed (Git) | OutputTransition + GitChangePayload |

`GitChangePayload` attaches to an OutputTransition and coexists with `ResultPayload`.
The patch text lives at `<run_dir>/artifacts/git/<payload_id>.patch`.

## Subcommands

```bash
stag git start  <input_transition_id>
stag git finish <session_id> [--status completed] [--summary TEXT]
                             [--matched-prediction <ot_id>]
                             [--artifact PATH] [--metric k=v] ...
stag git finish <session_id> --output-transition <ot_id>
stag git status
stag git diff   <session_id> | --output-transition <ot_id>
stag git log    <session_id> | --output-transition <ot_id>
```

## Basic flow

```bash
stag plan --run demo --input-node n_0000 --intent "add Git payload support"

stag git start it_0001
# -> gs_0001 (pending session)

# edit files + git commit

stag git finish gs_0001 --status completed --summary "added MVP"
# -> creates new OutputTransition + ResultPayload + GitChangePayload (form A)
```

## Attach Git data to an existing observation (form B)

```bash
stag observe it_0001 --status completed
# -> ot_0003 with ResultPayload
stag git finish gs_0001 --output-transition ot_0003
# -> attaches only a GitChangePayload to ot_0003
```

Form B rejects `--matched-prediction` and ResultPayload-mutating options.
The result semantics are owned by the original `observe`.

## MVP constraints

- detached HEAD at `start` is an error.
- branch switches between `start` and `finish` are errors.
- tracked-file dirty state at `finish` is an error. Untracked files are allowed.
- empty diffs (base == HEAD) emit a warning but the payload is attached normally.
- Form A on an InputTransition that already has an observed OT emits a warning
  recommending `--output-transition`.

## On-disk layout

```text
<run_dir>/git/sessions/gs_0001.json     # pending session
<run_dir>/git/current.json              # pointer to the last started session
<run_dir>/artifacts/git/pl_0008.patch   # patch text for a GitChangePayload
```

See `docs/ja/GIT_INTEGRATION.md` for the full specification.
""",
}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

GUIDES: dict[str, dict[str, str]] = {
    "ja": TOPICS_JA,
    "en": TOPICS_EN,
}

TOPIC_SUMMARIES: dict[str, str] = {
    "overview":  "Concept, RunGraph model, basic loop",
    "agent":     "Rules and anti-patterns for LLM agents using stag",
    "dump":      "stag dump output formats and symbols",
    "record":    "Typical workflow to record one experiment",
    "payloads":  "Payload types, attachment targets, Prediction/Result exclusivity",
    "cut":    "Append-only invalidation; IT cut vs OT cut",
    "joins":     "Multi-input transitions and how dump renders them",
    "git":       "Record Git commits / diffs as a payload on an OutputTransition",
}

_DEFAULT_TOPIC = "overview"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_guide_command(*, lang: str = "en", topic: str = _DEFAULT_TOPIC) -> dict:
    """Return the guide text for *topic* in *lang*.

    Returns a dict with keys ``guide``, ``lang``, ``topic``.
    Raises ``ValueError`` for an unknown topic.
    """
    topics = GUIDES[lang]
    if topic not in topics:
        valid = ", ".join(sorted(topics))
        raise ValueError(f"Unknown topic {topic!r}. Valid topics: {valid}")
    return {"guide": topics[topic], "lang": lang, "topic": topic}


def run_guide_list(lang: str = "en") -> dict:
    """Return topic id + summary pairs for *lang*."""
    topics = GUIDES[lang]
    return {
        "topics": [
            {"id": tid, "summary": TOPIC_SUMMARIES.get(tid, "")}
            for tid in topics
        ],
        "lang": lang,
    }


# ---------------------------------------------------------------------------
# argparse registration
# ---------------------------------------------------------------------------


def add_parser(subparsers) -> argparse.ArgumentParser:
    """Register the ``guide`` subcommand parser."""
    parser = subparsers.add_parser(
        "guide",
        help="Show the stag concept and CLI workflow guide",
        description="Show the stag concept, graph structure, and CLI workflow guide.",
    )
    parser.add_argument(
        "--lang",
        choices=sorted(GUIDES),
        default="en",
        help="Guide language (default: en)",
    )
    parser.add_argument(
        "--topic",
        default=None,
        metavar="NAME",
        help="Show a specific subtopic (see --list for names)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_topics",
        help="List available topic names and descriptions",
    )
    return parser


def cli_guide(args) -> int:
    """Entry point for ``stag guide`` subcommand."""
    if args.list_topics:
        result = run_guide_list(lang=args.lang)
        for entry in result["topics"]:
            print(f"  {entry['id']:<12}  {entry['summary']}")
        return 0

    topic = args.topic if args.topic is not None else _DEFAULT_TOPIC
    try:
        result = run_guide_command(lang=args.lang, topic=topic)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("Run `stag guide --list` to see available topics.", file=sys.stderr)
        return 1

    print(result["guide"])
    return 0
