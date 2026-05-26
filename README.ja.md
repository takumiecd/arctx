# STAG

![STAG Demo Video](examples/demo.gif)

STAG は、問題解決や最適化の過程を DAG と JSONL で記録するための Python ライブラリです。

最終成果だけでなく、途中で立てた plan、実行前の予測、実際に起きた結果を残すことを目的にしています。現在は 0.1 alpha で、後方互換よりもモデル整理を優先します。古い run 保存形式や旧 API との互換は保証しません。

## 何を構築しているか

STAG が構築しているのは、最適化プロセスのための append-only な履歴グラフです。

コード最適化、カーネル最適化、実験、調査では、最終的な成果物だけでなく、途中で何を試し、どうなると予測し、実際に何が起きたかが重要になります。STAG は、その試行錯誤を `RunGraph` と payload の形で保存します。

CLI や Python API は、この履歴グラフを操作するための入口です。`init` で run を作り、`transition create` で次の transition と output node を記録し、`payload add` で domain data を attach します。`graph trace` や `show` は、保存された判断の過程を読み返すために使います。

STAG 自体は executor や code generator ではありません。人間、LLM、script、benchmark runner、executor が行った判断や結果を、あとから共有・検証できる構造として残すための基盤です。

## モデル

0.1 の中心は `RunGraph` です。`RunGraph` が run 全体の DAG を持ち、`GraphView` がその部分集合を表します。

```text
RunHandle
  └── run_graph: RunGraph

RunGraph
  ├── nodes
  ├── transitions
  ├── payloads
  └── views

GraphView
  ├── view_id
  └── root_node_id
```

`Transition` は複数 input node から必ず 1 つの output node へ接続します。domain-specific な意味は payload として attach します。汎用の `NodePayload` / `TransitionPayload` に加えて、core の無効化意味論は `CutPayload` で表します。`GitChangePayload` などの git 固有 payload は標準 `git` extension 側にあります。

`RunGraph` は append-only です。一度追加した node / input transition / output transition / payload は削除せず、取り消しや無効化は `CutPayload` と read-time の計算で表します。

## Quick Start

```python
import stag
from stag import NodePayload, Requirement, TransitionPayload
from stag.storage import JsonlRunStore

requirement = Requirement(
    requirement_id="req_kernel",
    target_type="kernel",
    target_id="csc_linear",
)

run = stag.init(requirement, run_id="demo")

transition = run.transition(
    [run.root_node_id],
    TransitionPayload(
        payload_id="pending",
        target_id="pending",
        type="experiment",
        content={"intent": "run baseline benchmark"},
    ),
)

run.attach(
    transition.output_node_id,
    NodePayload(
        payload_id="pending",
        target_id="pending",
        type="result",
        content={"latency_ms": 1.5, "status": "completed"},
    ),
)

history = run.trace(transition.output_node_id)

store = JsonlRunStore("runs")
run.save(store)
loaded = store.load_run("demo")
```

隔離した探索をしたい場合は `GraphView` を作ります。`GraphView` は `root_node_id` だけを持ち、内容は read-time に `RunGraph.reachable_from(root_node_id)` で算出します。

## Install

Python 3.10 以上が必要です。

開発中の checkout から使う場合は、repo root で editable install します。

```bash
python3 -m pip install -e .
```

開発用 dependency も入れる場合は次を使います。

```bash
python3 -m pip install -e ".[dev]"
```

インストールせずに試す場合は、repo root で `PYTHONPATH=src python3 -m stag.cli.main ...` として実行できます。

## CLI Quick Start

CLI から概念と基本ループを確認するには、次を実行します。

```bash
stag guide
```

日本語で表示したい場合は `stag guide --lang ja` を使います。

```bash
stag init req_kernel \
  --target-type kernel \
  --target-id csc_linear \
  --run-id demo

stag transition create \
  --run demo \
  --from <root_node_id> \
  --payload-type transition_payload \
  --field type=experiment \
  --field intent="run baseline benchmark"
```

並列ターミナルや子プロセスでは、work session で履歴を分けます。毎回明示モードでは、
各 mutating command に `--run` と `--work-session` を渡します。

```bash
stag transition create \
  --run demo \
  --work-session ws_a \
  --from <root_node_id> \
  --payload-type transition_payload \
  --field type=experiment
```

固定モードでは、共有の `current.json` ではなく、現在の shell 環境だけに run/session
を固定します。

```bash
eval "$(stag work-session env --run demo --new)"
stag transition create --from <root_node_id> --payload-type transition_payload
stag work-session spawn --run demo -- codex
```

```bash
stag payload add \
  --run demo \
  --node <output_node_id> \
  --payload-type node_payload \
  --field type=result \
  --field latency_ms=1.5

stag graph trace --run demo <output_node_id>
stag show --run demo
```

git 連携は標準 extension です。正式な CLI namespace は `stag git ...` で、
`stag commit` や `stag verify` はそれぞれ `stag git commit` / `stag git verify`
への default alias として動きます。

```bash
stag init req_kernel --extension git --run-id demo
stag git commit -m "run baseline benchmark"
stag commit -m "try tiled kernel"
stag git verify
```

未インストールで同じ操作をする場合は、各 command を `PYTHONPATH=src python3 -m stag.cli.main ...` に置き換えます。

## 主な用語

- `Requirement`: run の目的。
- `RunGraph`: run 全体の DAG と global records。
- `GraphView`: `RunGraph` の部分集合。
- `Node`: pure graph node。
- `Transition`: 複数 input node を受け取り、1 つの output node を作る pure graph transition。
- `NodePayload`: node に attach される汎用 payload。
- `TransitionPayload`: transition に attach される汎用 payload。
- `CutPayload`: input / output transition の無効化を append-only に表す payload。
- `GitChangePayload`: git extension が transition に attach する payload。

## 保存形式

`JsonlRunStore` は run をディレクトリとして保存します。

```text
<store-dir>/<run-id>/
  run.json
  graph.json
  views.jsonl
  nodes.jsonl
  input_transitions.jsonl
  output_transitions.jsonl
  payloads.jsonl
```

0.1 alpha では保存形式を破壊的に変える可能性があります。旧 `states.jsonl` / `execution_plans.jsonl` 形式との読み込み互換は持たせません。

## ドキュメント

- [コンセプト](docs/ja/CONCEPT.md)
- [プロジェクトの方向性](docs/ja/DIRECTION.md)
- [状態モデル](docs/ja/STATE_MODEL.md)
- [API](docs/ja/API.md)
- [CLI](docs/ja/CLI.md)
- [問題解決ループ](docs/ja/AGENT_LOOP.md)

English documentation is also available under [docs/en/](docs/en/).

## 開発

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests -q
```

## License

MIT
