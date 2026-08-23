# ARCTX

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/arctx-mark-dark.svg">
    <img src="assets/arctx-mark.svg" alt="ARCTX" width="120">
  </picture>
</p>

[![CI](https://github.com/takumiecd/arctx/actions/workflows/ci.yml/badge.svg)](https://github.com/takumiecd/arctx/actions/workflows/ci.yml)

> **ARCTX は、仮説・試行・結果・放棄した枝を append-only な DAG として残す experiment graph です。**
>
> Git は何が変わったかを記録する。ARCTX は、何を試し、なぜ試し、何が起き、何が残ったかを記録する。

**30 秒で体感** — 1 コマンドで使い捨ての repo を立ち上げ、同じベースラインから
2 つの最適化仮説を試し、片方の行き止まりが *理由つきで* cut され、その全過程が
共有可能なドキュメントとして export されます:

```bash
git clone https://github.com/takumiecd/arctx && cd arctx
./examples/quickstart_demo.sh      # グラフを表示し、共有可能な HTML を書き出す
```

![ARCTX web GUI — baseline, a cut dead-end, and the winning branch](examples/demo_web.gif)

*`quickstart_demo.sh` が記録するもの: 両方の仮説が 1 つのベースラインから fan-out し、遅いキャッシュ案は **理由つきで** cut (✂) され、組み込み `sum()` の勝者は active のまま残る — その判断全体が 1 つのグラフに残ります。*

## パッケージ

本線は **`arctx`（コア）と `arctx-cli`** の 2 パッケージです。

| パッケージ | インストール | インポート | 用途 |
|---------|---------|--------|---------|
| `arctx` | `pip install arctx` | `import arctx` | コア API・ストレージ・拡張（CLI 依存なし）|
| `arctx-cli` | `pip install arctx-cli` | `import arctx_cli` | `arctx` コマンド、argparse CLI |

`arctx-cli` は `arctx` に依存します。通常は `arctx-cli` を入れれば `arctx` も入ります。

```python
import arctx

handle = arctx.init(arctx.Requirement(requirement_id="r", target_type="code", target_id="r"))
```

---

ARCTX は agent framework でも planner でも executor でも **ありません**。
研究・最適化・デバッグ・エージェント作業の下に位置するグラフ層です。

![ARCTX CLI Demo](examples/demo_cli.gif)

*同じ run に対して 2 つの AI エージェント（Claude と Codex）が並列に作業。各自が独立した `lane` を持ち、両ブランチは同じ `RunGraph` に兄弟 step として着地する — レースも上書きもなし。*

> 0.4 beta — DAG コア（Node / Step / Payload）は安定化しつつあります。ストレージや API の変更はまだあり得ますが、リリースノートに記載します。

*English version: [README.md](README.md).*

---

## なぜ ARCTX か？

研究や最適化の作業は一直線ではありません。仮説を立て、試し、何が起きたかを観測し、ある
ブランチを捨て、別を取り、後で *なぜ* その地点に至ったかを再構成する必要が出てきます。

- Git は **ファイル履歴** — どの commit でどのバイトが変わったか。
- ARCTX は **実験 / 推論 / 判断の履歴** — どの仮説を検証し、どんな結果が出て、どのブランチを cut したか。

ARCTX はそのすべてを 1 つの append-only な DAG として記録します:

- **仮説が branch になる。** 競合する試行は、単なるログに押し潰されず、同じベースラインから fan-out できます。
- **失敗した実験も資産として残る。** 放棄した枝は削除されず、`CutPayload` で inactive にされます。何を試し、なぜやめたかを後から見られます。
- **commit だけでなくドメイン payload。** ベンチマーク結果・予測・意図など何でも attach できます。DAG は各 step が *何のため* だったかを知っています。
- **並列エージェント、衝突なし。** 複数のエージェントや人間が同じ run を駆動でき、各自が追跡された lane を持ち、その試行は兄弟 step になります。
- **read-time の活性判定。** kill されたブランチは自動でフィルタされ、履歴を書き換えずにグラフはクリーンに保たれます。

ARCTX は executor でも planner でも agent framework でも *ありません*。それらが何をして
なぜしたか、何を試して捨てたかを保存する基盤です。

---

## ARCTX が合う場面は？

- **リサーチ・設計探索** — 仮説を分岐させ、結果を payload として記録し、捨てたブランチを証拠として残す。
- **最適化作業** — variant を比較し、ベースラインを明示し、遅い経路を捨てた理由を残す。
- **ベンチマーク駆動の工学** — 「variant A を試す、variant B を試す」が毎回、計測を attach した step として着地。
- **カーネル / 数値最適化** — 上記の具体例: タイル化 / ベクトル化 / 融合の実験を兄弟 step として、revert と merge を first-class に。
- **デバッグ・調査** — 仮説と観測を payload として記録し、バグを見つけたらトレースを遡る。
- **マルチエージェントのソフトウェア作業** — Claude Code・Codex・自作エージェント・人間が同じコードベースで作業。ARCTX は各試行を区別しレビュー可能に保ちます。

---

### 例 1: ベンチマーク駆動の最適化

variant A を試すと遅くなる。variant B を試すと速くなる。3 か月後、*なぜ* variant A を
捨てたか説明する必要が出てきます。

```bash
# 1. ベースライン。実験が分岐できるよう node id を取得しておく。
arctx init optimize --extension git --run-id bench
echo "def f(): pass" > work.py && git add work.py
BASE=$(arctx git commit -m "baseline: naive loop" | jq -r .output_node_id)

# 2. 仮説 A — キャッシュ層を追加。ベースライン node から分岐させる。
git checkout -b feat/cache
# ...edit...
git add .
A=$(arctx git commit -m "add cache (hypothesis A)" --from "$BASE" | jq -r .output_node_id)
arctx attach "$A" --type benchmark \
  --json '{"elapsed_ms": 1200, "note": "slower than baseline"}'

# 3. A を放棄 — グラフには残り、理由つきで inactive になるだけ。
arctx cut "$A" --reason "slower than baseline"

# 4. 仮説 B — ベクトル化。同じベースライン node から分岐させる。
git checkout main && git checkout -b feat/vectorize
# ...edit...
git add .
B=$(arctx git commit -m "vectorize (hypothesis B)" --from "$BASE" | jq -r .output_node_id)
arctx attach "$B" --type benchmark \
  --json '{"elapsed_ms": 180, "note": "5x faster than baseline"}'
```

`--from "$BASE"` は両実験をベースライン node に固定するため、（チェーンせず）真の
兄弟として fan-out します（チェーンだと A を cut すると B まで道連れになる）。
できあがるグラフが全過程を語ります — `arctx export --format md --full-payloads` を実行:

```text
n_root
└─ baseline ── n_baseline
   ├─ add cache (hypothesis A) ── n_A ✂
   │     benchmark {"elapsed_ms": 1200, "note": "slower than baseline"} · cut: slower than baseline
   └─ vectorize (hypothesis B) ── n_B
         benchmark {"elapsed_ms": 180, "note": "5x faster than baseline"}
```

スプレッドシートも古びた Confluence ページも要りません — *推論* が *コード* の隣に残ります。

---

### 例 2: マルチエージェント並列作業

Claude と Codex が、互いに踏まないように同じ run を駆動します。

```bash
# 共有ベースライン。両エージェントはこの node id から作業を分岐する。
BASE=$(arctx git commit -m "baseline" --run demo | jq -r .output_node_id)

# ターミナル 1 — Claude。run と lane をこのターミナルにだけ固定する。
eval "$(arctx use demo --shell)"
arctx lane create claude --purpose "内側ループのベクトル化" --user claude
eval "$(arctx lane switch claude --shell)"
export ARCTX_USER_ID=claude
git checkout -b claude/vec
# ...edits...
git add . && arctx git commit -m "Claude: vectorize inner loop" --from "$BASE"

# ターミナル 2 — Codex（同時に実行）
eval "$(arctx use demo --shell)"
arctx lane create codex --purpose "parallel map" --user codex
eval "$(arctx lane switch codex --shell)"
export ARCTX_USER_ID=codex
git checkout main && git checkout -b codex/map
# ...edits...
git add . && arctx git commit -m "Codex: parallel map" --from "$BASE"
```

両者は同じ `RunGraph` にベースラインからの兄弟 step として着地します。各エージェントは
自分の lane を持ち、`--from "$BASE"` が独立性を保つ — fast-forward 衝突も
上書きもありません:

```text
n_root
└─ baseline ── n_baseline
   ├─ Claude: vectorize inner loop ── n_2   (lane: claude / ws_xxx)
   └─ Codex: parallel map           ── n_3   (lane: codex / ws_yyy)
```

グラフ上に merge conflict はありません。両試行は永続的にレビュー可能なままです。

---

### 例 3: デバッグトレース

バグを追う過程で各仮説を記録し、原因を見つけたらそれを遡ります。

```bash
arctx init debug --extension git --run-id bug-42
echo "# repro" > repro.py && git add repro.py
REPRO=$(arctx git commit -m "reproduction script" | jq -r .output_node_id)

# 仮説: キャッシュの race condition
git checkout -b try/race-fix
# ...edit...
git add .
R=$(arctx git commit -m "fix: add lock around cache" --from "$REPRO" | jq -r .output_node_id)
arctx attach "$R" --type observation --json '{"result": "still flaky"}'

# 仮説: index の off-by-one
git checkout main && git checkout -b try/index-fix
# ...edit...
git add .
I=$(arctx git commit -m "fix: correct loop bound" --from "$REPRO" | jq -r .output_node_id)
arctx attach "$I" --type observation --json '{"result": "bug gone - 3 runs green"}'
```

両仮説は reproduction node から分岐するので、独立かつ比較可能なまま残ります:

```text
n_root
└─ reproduction script ── n_repro
   ├─ fix: add lock around cache ── n_2
   │     observation {"result": "still flaky"}
   └─ fix: correct loop bound    ── n_3
         observation {"result": "bug gone — 3 runs green"}
```

同僚に *「なぜ loop bound だと分かったの？」* と聞かれたとき、グラフが代わりに答えてくれます。

---

### 例 4: 1 つの主題、2 つのブランチ、1 つの結論

`lane` が「作業の束」、table が「数値の束」なら、**topic は「意味の束」**です。
グラフのどこにある node / step でも主題に tag でき、それが何を意味するかを読めます。

```bash
arctx topic tag l2-tiling "$CLAUDE_RESULT"
arctx topic tag l2-tiling "$CODEX_RESULT"     # もう一方のブランチの record
```

連結性は要求も検証もされません。ただし 2 つ目の tag は、この主題が**出会ったことの
ない 2 つの系譜にまたがった**ことに気づき、出口を全部「実行できるコマンド」として
提示します:

```text
notice: topic "l2-tiling" spans 2 unjoined islands
  island 1  1 records  tip n_b003732a  (lane claude)
  island 2  1 records  tip n_8744ba41  (lane codex)
  both are right, under different conditions
    → arctx topic join l2-tiling --summary "..."
  they turned out to be two subjects
    → arctx topic split l2-tiling --island 2 --into NEW_NAME --summary "..."
  island 2 was a dead end
    → arctx cut n_8744ba41 --reason "..."
  the tag was a mistake
    → arctx topic untag l2-tiling n_8744ba41
```

分かれた主題は**抱えたままの矛盾**であり、出口はちょうど 4 つしかありません。1 つ
選びます:

```bash
arctx topic join l2-tiling \
  --summary "128 tiles win on both branches; the map path just needed the same bound"
# joined 2 lineages of topic "l2-tiling" — 1 island now
```

join は各島の tip から出る本物の Step なので、結論は両方の**後に来る node**です。
だから `--summary` が必須になります（`lane close` と同じ規律）。join に「正しい側」は
ありません — 入力は集合です。

```bash
arctx topics
# l2-tiling  ·  3 records · 1 islands  ·  128 tiles win on both branches; ...
```

`arctx guide --context` は上位の結論文と、**まだ分かれたままの topic** を意図的に
表示します — 「まだ噛み合っていない 2 つのことを知っている」場所です。
`arctx topic log <name>` は結論文の変遷を古い信念から現在まで辿ります。
かつてそう考えていたこと自体も証拠だからです。

---

## 30 秒クイックスタート

git repository の中から:

```bash
pip install arctx-cli

arctx init my_task --extension git --run-id demo
echo "def f(): pass" > work.py && git add work.py
BASE=$(arctx git commit -m "baseline" | jq -r .output_node_id)

arctx log                              # DAG を歩く
arctx dump --format outline            # または LLM 向けの outline でダンプ
arctx dump --format mermaid            # または視覚的な mermaid flowchart
```

`arctx dump` が正準の run 全体レンダラーで、`arctx graph dump` は `graph` 名前空間下の同等物です。

同じ repo で 2 エージェント？ 各自が独立した lane を持ち、互いの attribution に
触れません:

```bash
# Claude のターミナル
eval "$(arctx use demo --shell)"
arctx lane create claude --purpose "vectorization" --user claude
eval "$(arctx lane switch claude --shell)"
export ARCTX_USER_ID=claude
git checkout -b claude/vec
# ...edits...
git add . && arctx git commit -m "Claude: vectorization" --from "$BASE"

# Codex のターミナル（並列に実行）
eval "$(arctx use demo --shell)"
arctx lane create codex --purpose "parallel map" --user codex
eval "$(arctx lane switch codex --shell)"
export ARCTX_USER_ID=codex
git checkout main && git checkout -b codex/map
# ...edits...
git add . && arctx git commit -m "Codex: parallel map" --from "$BASE"
```

両ブランチは同じ `RunGraph` に `$BASE` からの兄弟 step として着地します。実行可能な
VHS 録画はこのシナリオの `examples/demo_cli.tape` と `examples/demo_env.sh` を参照してください。

![ARCTX multi-agent graph — Claude and Codex as sibling steps off one baseline](examples/arctx-multi-agent-graph.png)

*2 エージェント、1 つの run: 各 commit は自分の `lane` に attribution され、両者は共有ベースラインからの兄弟 step として着地する — レースも上書きもなし。*

> **隔離についての注意。** ARCTX の `lane` は ARCTX の run/session attribution（誰が、どのセッションで何をしたか）を隔離します。それ単体では Git の working tree は隔離 **しません** — 各セッションを自分の `git worktree` に attach しない限り、上の 2 ターミナルは同じ checkout を共有します。worktree 対応版は次節を参照してください。

### 別々の worktree での並列エージェント

`arctx` は各エージェントを専用の `git worktree` に固定でき、2 つのターミナルが互いを
踏まずに編集・stage・commit できます:

```bash
# 独立したブランチで 2 つの worktree を用意。
arctx git worktree add ../wt-claude claude/vec
arctx git worktree add ../wt-codex  codex/map

# 各ターミナルが run / lane / user / worktree を自分で固定する。git verb
# (`arctx git commit`, `revert`, `merge` ...) は ARCTX_GIT_WORKTREE を読み、
# shell の cwd ではなくそこで git サブプロセスを実行する。
eval "$(arctx use demo --shell)"
arctx lane create claude --purpose "vectorization" --user claude
eval "$(arctx lane switch claude --shell)"
export ARCTX_USER_ID=claude
export ARCTX_GIT_WORKTREE=../wt-claude
```

両エージェントとも依然として同じ `RunGraph` に兄弟 step として commit を着地させます。
worktree は物理的な checkout を分けるだけです。

---

## 概念（1 画面）

ARCTX の中心は **`RunGraph`** — append-only な DAG です。純粋なグラフ record は
ドメインデータを持たず、ドメイン固有のものはすべて **Payload** record に載ります。

```text
RunGraph
  ├── Node         ← 純粋な DAG node
  ├── Step         ← N 個の入力 node → 1 個の出力 node
  └── Payload      ← Node または Step に付く注釈
```

- 各 **試行 / 実験 / アクションは step として記録され**、結果状態を表す出力 node を生成します。
- `NodePayload` / `StepPayload` — `type` 文字列で区別される汎用注釈。
- `CutPayload` — append-only な無効化。対象は削除されず、read-time にフィルタされます。
- `GitChangePayload` — `git` extension が `arctx git commit` ごとに attach します。

活性（「この node はまだスコープ内か？」）は `RunGraph` + cut payload から read-time に
計算されます。ストアが書き換えられることはありません。

---

## CLI 要点

| コマンド | 何をするか |
| --- | --- |
| `arctx init <req-id>` | 新しい run を開始する。git 連携には `--extension git` を付ける。 |
| `arctx add --from <node> --title ...` | DAG step とその出力 node を追加する。node は単独では作らない。 |
| `arctx attach <node-or-step> --title ...` | 既存の node または step に payload を attach する。 |
| `arctx cut <node-or-step>` | append-only payload で node または step を inactive にする。 |
| `arctx show [id]` | 現在の run、または 1 件の node/step/payload を表示する。 |
| `arctx log` | DAG を順序付きイベントストリームとして表示する。 |
| `arctx git commit -m ...` | 実際の `git commit` を駆動し、`GitChangePayload` 付きの `Step` を記録する。 |
| `arctx lane create <name>` | lane を開く。フラットで git ブランチのような作業単位。purpose を持ち、close には summary が必須。 |
| `arctx lane switch <name> --shell` | `export ARCTX_LANE_ID=…` を出力し、repo 全体のポインタを書かずにこのターミナルだけ lane を切り替える。 |
| `arctx topic tag <name> <id>...` | グラフを横断して record を「意味の束」にまとめる。連結性は要求されない — 島が 2 つ以上なのは join の*候補*であってエラーではない。 |
| `arctx topic summarize <name> --summary ...` | その主題の現在の結論文。`arctx topics` が全 topic を結論文と島数つきで一覧する。 |
| `arctx git worktree add <path> [branch]` | `git worktree add` の薄いラッパー。`ARCTX_GIT_WORKTREE=<path>` を export すると git verb がその中で走る。 |
| `arctx dump --format outline` | run 全体を LLM 向けのインデント spanning-tree でダンプする。 |
| `arctx dump --format mermaid` | 人間 / docs 向けの mermaid flowchart。 |

`arctx graph dump ...` は `graph` 名前空間下の同等形式です。

完全なリファレンス: [docs/ja/CLI.md](docs/ja/CLI.md)。

変更系コマンドは対象 run を次の順で解決します: `--run` フラグ → `ARCTX_RUN_ID` 環境変数 → 最寄りの git repo の `.arctx-id`。user attribution: `--user` → `ARCTX_USER_ID` → `<ARCTX_HOME>/config.json` → `"user"`。

---

## Python API

```python
import arctx as arctx
from arctx import NodePayload, Requirement, StepPayload
from arctx.storage import JsonlRunStore

requirement = Requirement(
    requirement_id="req_demo",
    target_type="task",
    target_id="explore_idea",
)

run = arctx.init(requirement, run_id="demo")

step = run.add_step(
    [run.root_node_id],
    StepPayload(
        payload_id="pending",
        target_id="pending",
        type="experiment",
        content={"intent": "try the first hypothesis"},
    ),
)

run.attach(
    step.output_node_id,
    NodePayload(
        payload_id="pending",
        target_id="pending",
        type="result",
        content={"observation": "promising", "status": "completed"},
    ),
)

history = run.trace(step.output_node_id)

store = JsonlRunStore("runs")
run.save(store)
loaded = store.load_run("demo")
```

---

## インストール

Python 3.10+ が必要です。

```bash
python3 -m pip install -e .            # editable install
python3 -m pip install -e ".[dev]"     # + dev dependencies

# またはインストールせず、repo ルートから実行:
PYTHONPATH=src python3 -m arctx_cli.main ...
```

---

## ストレージレイアウト

`JsonlRunStore` は各 run をディレクトリとして永続化します:

```text
<store-dir>/<run-id>/
  run.json
  graph.json
  nodes.jsonl
  steps.jsonl
  payloads.jsonl
  lanes.jsonl
  lane_events.jsonl
```

`SqliteRunStore` は同じデータを run ごとの単一 `run.db` に保存します。デフォルトの
ストアディレクトリは `<repo_root>/.arctx/runs` です（git-native な in-repo ストレージ）。`ARCTX_HOME` を設定した場合と git repo 外では `<ARCTX_HOME>/runs` です。リポジトリの正典は json / jsonl のみで、`run.cache.pkl` / `run.db` は `arctx init` が生成する `.arctx/.gitignore` で除外されます。

`GraphView` / `views.jsonl` は 0.3 beta の再設計で削除されました。古い view record は
新しいコアグラフモデルでは無視されます。

---

## ドキュメント

- [Concept](docs/ja/CONCEPT.md)
- [Project Direction](docs/ja/DIRECTION.md)
- [State Model](docs/ja/STATE_MODEL.md)
- [API](docs/ja/API.md)
- [CLI](docs/ja/CLI.md)
- [Problem-Solving Loop](docs/ja/AGENT_LOOP.md)

English documentation is in [docs/en/](docs/en/).

---

## 開発

```bash
uv run --package arctx --extra dev pytest packages/arctx/tests -q
uv run --package arctx-cli --extra dev pytest packages/arctx-cli/tests -q
```

## リリース

メンテナ向けのリリース手順は [CONTRIBUTING.md](CONTRIBUTING.md#release-process) に記載しています。

## ライセンス

MIT
