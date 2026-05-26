# STAG

**並列に進む最適化作業を、1つも取りこぼさない append-only グラフ。** 複数の AI agent / 人間 / benchmark runner が、同じ run に対して branch・revert・merge しても、試行は1つも失われません。

![STAG CLI Demo](examples/demo_cli.gif)

*2つの AI agent (Claude と Codex) が同じ repo に並列で commit している様子。それぞれが独立した `work-session` を持ち、両方の branch は同じ `RunGraph` 内の sibling transition として記録されます。race condition も上書きも発生しません。*

![STAG TUI Demo](examples/demo_tui.gif)

*インタラクティブな 3-pane TUI で DAG を歩く: 各 experiment、revert、payload の diff、git の履歴が 1 画面で見渡せます。*

> 0.1 alpha — 破壊的変更があり得ます。モデル整理を優先しており、古い run 保存形式の移行サポートはありません。

*English version: see [README.md](README.md).*

---

## なぜ STAG か

実際の最適化作業は混沌としています。vectorization を試し、行き詰まり、multithreading を試し、deadlock になり、revert し、別の手を試す。今日その分岐は、頭の中、scratch メモ、そして「なぜ試したか」を語らない `git log --oneline` の中にしか残りません。

STAG はそれら全てを 1 つの append-only DAG として記録します:

- **並列 agent でも衝突しない。** Claude と Codex が同じ run に対して `stag git commit` できます。各々独立した work-session を持ちます。
- **revert しても履歴は残る。** 失敗した Rust 書き換えは削除されず、`CutPayload` で inactive とマークされます。何を試したか・なぜ捨てたかをあとから辿れます。
- **commit だけでなく domain payload を載せられる。** benchmark 結果、予測、意図 — 何でも attach できます。各 transition が「何のため」だったかを DAG が知っています。
- **active かどうかは read-time に計算。** 切り捨てた branch は自動で filter されます。履歴を書き換えずに、グラフは綺麗に保たれます。

STAG は executor / planner / agent framework ではありません。それらが「何をしたか」を保存するための基盤です。

---

## どんな時に使うか

- **並列 AI agent のオーケストレーション** — Claude Code、Codex、自作 agent が同じ codebase で作業する場合。各試行が区別され、あとからレビュー可能になります。
- **kernel / 数値最適化** — 「tiled で試す、vectorize で試す、fuse で試す」がそれぞれ node になります。revert / merge は first-class。
- **調査・デバッグ** — 仮説と観察結果を payload で記録し、原因にたどり着いた時点で trace を逆向きに歩けます。

---

## 30 秒で始める

```bash
pip install -e .

stag init my_task --extension git --run-id demo
echo "def f(): pass" > work.py && git add work.py
stag git commit -m "baseline"

stag tui          # DAG をインタラクティブに探索
stag dump         # もしくは LLM 向け outline でダンプ
```

同じ repo で 2 つの AI agent を並列に動かしたい場合、それぞれに独立した work-session を発行できます:

```bash
# Claude の端末
eval $(stag work-session env --run demo --new --user claude)
git checkout -b claude/vec
# ...編集...
git add . && stag git commit -m "Claude: vectorization"

# Codex の端末 (同時に動いていてよい)
eval $(stag work-session env --run demo --new --user codex)
git checkout main && git checkout -b codex/map
# ...編集...
git add . && stag git commit -m "Codex: parallel map"
```

両方の branch は同じ `RunGraph` 内の sibling transition として記録されます。実際に動く VHS デモは `examples/demo_cli.tape` と `examples/demo_env.sh` を参照してください。

---

## 概念 (1 画面)

STAG の中心は **`RunGraph`** — append-only な DAG です。pure な graph 記録は domain data を持たず、domain 固有の情報はすべて **Payload** 側に集約されます。

```text
RunGraph
  ├── Node         ← pure な DAG node
  ├── Transition   ← N 個の input node → 1 個の output node
  ├── Payload      ← Node または Transition に attach する注釈
  └── GraphView    ← 軽量な named scope (root_node_id のみ保持)
```

- `NodePayload` / `TransitionPayload` — 汎用の注釈。`type` 文字列で目的を区別します。
- `CutPayload` — append-only な無効化マーカー。対象は削除されず、read-time に filter されます。
- `GitChangePayload` — `git` extension が `stag git commit` のたびに attach する payload。

「この node はまだ生きているか」という activity 判定は、read 時に `RunGraph` と CutPayload から計算されます。store は決して書き換えません。

---

## CLI の主なコマンド

| コマンド | 用途 |
| --- | --- |
| `stag init <req-id>` | 新しい run を作成。`--extension git` で git 統合を有効化。 |
| `stag git commit -m ...` | 実際の `git commit` を実行し、`Transition` と `GitChangePayload` を記録。 |
| `stag work-session env --new --user <name>` | 端末/サブプロセス専用のシェル exports を出力。 |
| `stag transition create` | git なしで transition を追加。 |
| `stag payload add` | 既存 Node / Transition に payload を attach。 |
| `stag dump --format outline` | LLM 向けの indented spanning-tree でダンプ。 |
| `stag dump --format mermaid` | 人間/ドキュメント向け Mermaid flowchart。 |
| `stag tui` | 3-pane (Runs / Flowchart / Detail) のインタラクティブ TUI。 |
| `stag cut node <id>` | Node (とその下流) を inactive に。append-only。 |
| `stag guide` | 概念をインタラクティブに学ぶ (`--lang ja` で日本語)。 |

詳細リファレンス: [docs/ja/CLI.md](docs/ja/CLI.md)。

mutating コマンドの run 解決順は `--run` → `STAG_RUN_ID` 環境変数 → カレント git repo の `.stag-id`。user attribution は `--user` → `STAG_USER_ID` → `<STAG_HOME>/config.json` → `"user"`。

---

## Python API

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

部分集合を切り出して探索したい場合は `GraphView` を作成します。`GraphView` は `root_node_id` のみを保持し、内容は read 時に `RunGraph.reachable_from(root_node_id)` で導出されます。

---

## インストール

Python 3.10 以上が必要です。

```bash
python3 -m pip install -e .            # editable install
python3 -m pip install -e ".[dev]"     # + 開発依存

# インストールせずに repo root から実行する場合:
PYTHONPATH=src python3 -m stag.cli.main ...
```

---

## ストレージレイアウト

`JsonlRunStore` は run を以下のディレクトリ構造で保存します:

```text
<store-dir>/<run-id>/
  run.json
  graph.json
  nodes.jsonl
  transitions.jsonl
  payloads.jsonl
  views.jsonl
  work_sessions.jsonl
  work_events.jsonl
```

`SqliteRunStore` は同じ内容を per-run の `run.db` 1 ファイルにまとめます。デフォルトの store ディレクトリは `<STAG_HOME>/runs`。

0.1 alpha のため、スキーマは破壊的に変わる可能性があります。古い形式からの自動移行はありません。

---

## ドキュメント

- [コンセプト](docs/ja/CONCEPT.md)
- [プロジェクトの方向性](docs/ja/DIRECTION.md)
- [State モデル](docs/ja/STATE_MODEL.md)
- [API](docs/ja/API.md)
- [CLI](docs/ja/CLI.md)
- [問題解決ループ](docs/ja/AGENT_LOOP.md)

English docs: see [docs/en/](docs/en/).

---

## 開発

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests -q
```

## License

MIT
