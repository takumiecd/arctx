# Single-Output Transition + Generic Payload リファクタ計画

## 設計哲学

1. **関数的 Transition**: 複数 input → 1 つの action → **1 つの output Node**。`inputs → action → output` で 1:1 に追えること
2. **拡張は Python で**: ユーザーが新しい記録種別を増やしたければ `PayloadBase` を継承して自作する。これが基本路線
3. **デフォルトの逃げ道**: Python 書きたくないユーザー向けに、`type` + `content` を持つ generic な `NodePayload` / `TransitionPayload` を同梱。文字列 type で何でも記録できる
4. **必要最小限の built-in 特殊 Payload**: `CutPayload`（cascade 意味論があるので必須）、`GitChangePayload`（用途が普遍的なので便利）。それ以外（旧 Plan / Prediction / Result / Note）は廃止

## スキーマ

### Graph records

```python
@dataclass(frozen=True)
class Node:
    node_id: str
    metadata: dict[str, JSONValue] = field(default_factory=dict)

@dataclass(frozen=True)
class Transition:
    transition_id: str
    input_node_ids: tuple[str, ...]   # 複数 OK（multi-input join）
    output_node_id: str               # 必ず 1 つ
    metadata: dict[str, JSONValue] = field(default_factory=dict)
```

`Edge` は廃止。逆引きは `RunGraph` 内の dict で。

### Payload

```python
class PayloadBase(ABC):
    """すべての Payload の親。fix なのはこの 3 フィールドだけ。"""
    payload_id: str
    target_kind: Literal["node", "transition"]
    target_id: str
    payload_type: str  # シリアライズ時の dispatch key（subclass 名 / "node" / "transition" / "cut" / "git_change" 等）

    @abstractmethod
    def to_dict(self) -> dict[str, JSONValue]: ...
```

#### Built-in concrete payloads

```python
@dataclass(frozen=True)
class NodePayload(PayloadBase):
    """汎用 Node Payload。type 文字列で用途を分ける。"""
    payload_id: str
    target_id: str
    type: str                                  # free-form
    content: dict[str, JSONValue] = field(default_factory=dict)
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: Literal["node"] = field(default="node", init=False)
    payload_type: str = field(default="node_payload", init=False)


@dataclass(frozen=True)
class TransitionPayload(PayloadBase):
    """汎用 Transition Payload。type 文字列で用途を分ける。"""
    payload_id: str
    target_id: str
    type: str
    content: dict[str, JSONValue] = field(default_factory=dict)
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: Literal["transition"] = field(default="transition", init=False)
    payload_type: str = field(default="transition_payload", init=False)


@dataclass(frozen=True)
class CutPayload(PayloadBase):
    """append-only な無効化マーク。Node または Transition に貼る。
    cascade 判定の意味論を core が持つので built-in。
    """
    payload_id: str
    target_kind: Literal["node", "transition"]
    target_id: str
    reason: str | None = None
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    payload_type: str = field(default="cut", init=False)


@dataclass(frozen=True)
class GitChangePayload(PayloadBase):
    """Git の commit / diff 記録。Transition にのみ貼る（変更は action なので）。"""
    payload_id: str
    target_id: str
    branch: str
    head_commit: str
    diff_summary: DiffSummary
    commit_log: tuple[CommitEntry, ...] = ()
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: Literal["transition"] = field(default="transition", init=False)
    payload_type: str = field(default="git_change", init=False)
```

#### 廃止される旧 Payload

- `PlanPayload` — intent は generic `TransitionPayload(type="...")` の content で表現
- `PredictionPayload` / `ResultPayload` — 「予測か実測か」を type 名で表現（e.g., `type="suggestion"` vs `type="implementation"`）。マッチングしたい時は content に prior transition_id を入れる
- `NotePayload` — `NodePayload(type="note", content={"text": "..."})` で代替

#### ユーザー自作 subclass

ユーザーが自分のプロジェクトで `PayloadBase` を継承して、型付きフィールドを持つ custom Payload を作れる。例：

```python
# user_code.py
@dataclass(frozen=True)
class ExperimentResultPayload(PayloadBase):
    payload_id: str
    target_id: str
    metrics: dict[str, float]
    seed: int
    duration_sec: float

    target_kind: Literal["transition"] = field(default="transition", init=False)
    payload_type: str = field(default="experiment_result", init=False)
```

`isinstance(p, ExperimentResultPayload)` で型安全に取り出せる。

## RunGraph

```python
@dataclass
class RunGraph:
    nodes: dict[str, Node]
    transitions: dict[str, Transition]
    payloads: dict[str, PayloadBase]
    views: dict[str, GraphView]
    work_sessions: dict[str, WorkSession]
    work_events: list[WorkEvent]
    metadata: dict[str, JSONValue]

    # ---- 逆引きインデックス（永続化せず、ロード時に再構築） ----
    transitions_by_input_node: dict[str, list[str]]
    transition_by_output_node: dict[str, str]
    payloads_by_node: dict[str, list[str]]
    payloads_by_transition: dict[str, list[str]]
```

### 公開 API（lookup）

- `transitions_from_node(node_id) -> list[transition_id]`
- `transition_to_node(node_id) -> transition_id | None`
- `transition_inputs(transition_id) -> tuple[str, ...]`
- `transition_output(transition_id) -> str`
- `payloads_for_node(node_id, *, payload_type=None) -> list[PayloadBase]`
- `payloads_for_transition(transition_id, *, payload_type=None) -> list[PayloadBase]`

`transition_kind()` は廃止。kind は payload の type を見て呼び出し側が判断する。

## Verb（最小）

```python
run.transition(
    input_node_ids: list[str],
    payload: PayloadBase,                  # TransitionPayload subclass instance
    *,
    max_outcomes: int = 1,
    user_id, work_session_id,
) -> list[Transition]
```

- N 個の sibling Transition を生成、各 Transition に payload の **コピーを attach**（payload_id だけ振り直し）
- 戻り値は Transition のリスト
- max_outcomes=1 が普通（observation）。複数 sibling が欲しい時（予測の枝分かれ等）は ≥2

```python
run.attach(
    node_id: str,
    payload: PayloadBase,                  # NodePayload subclass instance
    *,
    user_id, work_session_id,
) -> PayloadBase
```

- Node に Payload を attach（汎用記録 / メモ / 任意の custom）

```python
run.cut(target_id: str, *, target_kind: Literal["node", "transition"], reason=None, ...) -> CutPayload
```

- Convenience。内部で `CutPayload` を attach

### 廃止

- `run.plan()` — `run.transition()` で代替
- `run.predict()` — `run.transition(..., max_outcomes=N)` で代替
- `run.observe()` — `run.transition(..., max_outcomes=1)` で代替
- `run.note()` — `run.attach(node_id, NodePayload(type="note", content={"text": ...}))` で代替（CLI には残してもいい convenience）

## CLI

破壊的変更。alpha なので互換性なし。

- `stag transition --inputs S0 --type suggestion --content '{"proposal": "..."}' [--max-outcomes N]` — generic do
- `stag attach <node> --type note --content '{"text": "..."}'` — node payload
- `stag cut <target>` — convenience
- `stag show` / `stag trace` / `stag outcomes` / `stag dump` — 新スキーマに追従
- `stag tui` — 新スキーマに追従

旧 `stag plan` / `stag predict` / `stag observe` / `stag note` は **削除**。convenience として残すかは後検討。

## Cut の意味（変更なし）

- Node に `CutPayload` → そのノード + 下流の Transition / output Node が inactive
- Transition に `CutPayload` → その Transition + output Node + 下流が inactive
- 「inactive」は read-time に計算（`inactive_node_ids` / `inactive_transition_ids`）

## ストレージ

新しい run directory 構造：

- `run.json` — 変更なし
- `graph.json` — RunGraph metadata + counters
- `nodes.jsonl`
- `transitions.jsonl` — `input_node_ids` と `output_node_id` を含む
- `payloads.jsonl` — `payload_type` で dispatch
- `views.jsonl`
- ~~`edges.jsonl`~~ — 削除
- ~~`input_transitions.jsonl` / `output_transitions.jsonl`~~ — 既に削除済み

旧形式の互換性は **持たない**。

### Payload deserialization

`payload_from_dict(data)` が `payload_type` フィールドを見て該当 class にディスパッチ。built-in は core が登録、ユーザー自作 subclass は明示的に登録 API で追加：

```python
from stag.core.schema.payloads import register_payload_class
register_payload_class(ExperimentResultPayload)
```

未登録の `payload_type` が出てきたら：

- (a) **fallback to generic**: 同じ target_kind の generic Payload (`NodePayload` / `TransitionPayload`) に変換、`type=元のpayload_type`、`content=元のフィールド全部` として読み込む
- (b) **error**: 未登録 type は load 失敗

MVP 案: **(a)** を採用。ユーザーが custom payload class を import せず CLI 触っても落ちない。

## TUI への影響

- Tree: Transition の output が 1 つに固定されるので、Transition → 単一 output Node の直線関係に。fan-out は **複数 sibling Transition** として表現
- Flowchart: 各 Transition は 1:N input + 1 output の標準形。layout が単純化
- Payload 表示: type ごとの特別 rendering は MVP では持たない。`type` / `content` を JSON dump で表示。Cut / GitChange は subclass なので typed access で綺麗に表示できる
- TUI が認識する built-in payload は `CutPayload` と `GitChangePayload` の 2 つ + 汎用の `NodePayload` / `TransitionPayload`

## 影響を受けるファイル（ざっくり）

- `src/stag/core/schema/graph.py` — `Edge`/`GraphRef`/`GraphRecordKind` 削除、`Transition` に `input_node_ids` / `output_node_id` 追加
- `src/stag/core/schema/payloads.py` — 全面書き直し。`PlanPayload` / `PredictionPayload` / `ResultPayload` / `NotePayload` 削除、`NodePayload` / `TransitionPayload` 新設、`CutPayload` / `GitChangePayload` 残す（API は調整）、`register_payload_class` API 新設
- `src/stag/core/run_graph.py` — Edge 関連 API 削除、逆引きインデックス
- `src/stag/core/run/plan.py` — **削除**
- `src/stag/core/run/predict.py` — **削除**（または rename）
- `src/stag/core/run/observe.py` — **削除**（または rename）
- `src/stag/core/run/transition.py` — 新規。`run.transition()` の実装
- `src/stag/core/run/attach.py` — 新規。`run.attach()`（or `run/note.py` を rename / 削除）
- `src/stag/core/run/cut.py` — 追従
- `src/stag/core/run/dump.py` — outline/mermaid を新スキーマで再実装
- `src/stag/core/run/trace.py` / `outcomes.py` — 追従
- `src/stag/core/cuts.py` — `CutPayload` ベースで再実装（変更小）
- `src/stag/storage/jsonl.py` / `sqlite.py` — `transitions.jsonl` のフォーマット変更、`edges.jsonl` 削除
- `src/stag/cli/main.py` 他 — verb 削除 / 新設
- `src/stag/tui/*` — 追従
- `tests/` — 全面書き直し
- `docs/ja/{DIRECTION,STATE_MODEL,API,CLI,AGENT_LOOP,CONCEPT}.md` — 更新
- `CLAUDE.md` — 更新

## 進め方

1. 本ドキュメントに合意
2. `feat/single-output-transition` ブランチで実装
3. 実装順: core schema → RunGraph → verb → storage → CLI → TUI
4. テスト全面再構築
5. docs / CLAUDE.md 更新

## 未決の論点（実装時に決める）

- `run.transition()` のシグネチャ詳細: `max_outcomes=1` で sibling 1 個か、`max_outcomes=N` で payload を N 個分受け取るか
- `run.attach()` という名前が良いか別の動詞か（`add_payload` 等）
- CLI で convenience verb (`stag note` 等) を完全削除するか、type="note" 用の shortcut として残すか
- `payload_from_dict` の fallback (a) を本当に許すか、registry 必須にするか
