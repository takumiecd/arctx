Multi-Actor Cursor Model 仕様書 v0.1

目的

optimization-agent の Run 操作を、単一の current_observed_state_id 中心のモデルから、複数 Actor が複数 Cursor を持って TraceDAG / PredictionDAG を探索するモデルへ移行する。

この変更の目的は、単一エージェントの逐次探索だけでなく、人間・サブエージェント・レビューエージェント・実験エージェントなどが同じ Run 内の DAG を共有しながら、それぞれ独立した視点で探索・比較・統合できるようにすることである。

基本方針

TraceDAG と PredictionDAG は、append-only な探索ログとして扱う。State / Plan / Transition は、過去に実際に作られた記録として基本的に書き換えない。一方、Cursor は mutable な視点として扱い、Actor ごとに自由に移動できる。

Run 自体は単一の current state を持たない方向へ移行する。代わりに、各 Cursor が current_state_id を持つ。人間用のデフォルト Cursor として main を作り、既存の単一 current state 的な操作は main Cursor を通じて互換的に扱う。

DAG 本体から depth を取り除く。TraceDAG / PredictionDAG は「深さ付きDAG」ではなく、通常の DAG として扱う。depth は graph の本質的な属性ではなく、表示・検索・UI・trace view のために必要なとき計算される derived view / derived index とする。

中心概念

Run

Run は一つの問題解決・最適化探索の単位である。Run は共有される TraceDAG / PredictionDAG と、Actor / Cursor の集合を持つ。

Run は「現在位置」を直接持つのではなく、Cursor 群を持つ。既存互換のために current_observed_state_id を残す場合でも、それは main Cursor の current_state_id の別名として扱う。

Actor

Actor は Cursor を所有できる主体である。人間ユーザー、サブエージェント、ワーカー、レビュー担当、プランナーなどを同じ仕組みで表現する。

Actor は少なくとも次の種類を持つ。

human

agent

将来的には system, worker, reviewer, planner, executor などを追加してもよい。

Cursor

Cursor は DAG 上の State を指す mutable pointer である。

Cursor は Actor に所有される。1つの Actor は複数の Cursor を持ってよい。たとえば、人間は main, compare, review などの Cursor を持てる。サブエージェントは自分専用の探索 Cursor を持てる。

Cursor は State / Plan / Transition と違って、自由に移動できる。ただし、移動操作の履歴は必要に応じて CursorEvent として記録できる。

TraceDAG

TraceDAG は観測済みの実行履歴を保存する append-only graph である。

TraceDAG の State は observed state であり、ObservedTransition は実際に実行された ActionResult を伴う。

TraceDAG には複数 Actor / Cursor からの探索結果が全て追加される。したがって、TraceDAG は「1本の正解ルート」ではなく、「試された探索全体の地図」である。

PredictionDAG

PredictionDAG は未実行の未来候補を保存する append-only graph である。

従来は Run に1つの PredictionDAG があり、Run の current observed state を anchor にしていた。Cursor-first モデルでは、PredictionDAG は Cursor に紐づけて扱えるようにする。

最小実装では Run に1つの PredictionDAG を維持しつつ、anchor_cursor_id と anchor_state_id を保存する。将来的には Cursor ごと、または workspace ごとに複数 PredictionDAG を持てるようにする。

Depth 方針

Depth は DAG 本体の一部ではない

これまで TraceDAG / PredictionDAG は node_depths や nodes_by_depth を持つ depth-oriented DAG として扱っていた。しかし、Cursor-first / multi-actor モデルでは、depth を DAG の本質的な構造として持つと設計が硬くなる。

今後は、DAG 本体は次だけを持つ。

nodes
plans
transitions
incoming_index
outgoing_index

node_depths と nodes_by_depth は DAG の source-of-truth から外す。

Depth は derived view として計算する

必要な場合だけ、root や cursor からの距離として depth を計算する。

たとえば、表示や trace context では次のような関数を使う。

compute_depths_from_root(dag) -> dict[str, int]
compute_depths_from_cursor(dag, cursor_id) -> dict[str, int]
active_path(cursor_id) -> list[str]

このとき depth はあくまで表示・検索・並び替え用の補助情報であり、Plan 作成や rollback の正しさ判定には使わない。

Rollback は depth ではなく ancestor 判定で行う

rollback の判定は、target.depth < current.depth ではなく、target is ancestor of current で行う。

OK:  current から incoming edge を辿って target に到達できる
NG:  depth が浅いだけで ancestor ではない別枝の state

別枝へ移動する操作は rollback ではなく switch / move として扱う。

Plan は depth に依存しない

Plan は depth ではなく State の内容と input state set に依存して作られる。

したがって、異なる深さにある State 同士からでも、必要なら同じ PlanSpec を使って Plan を作ってよい。

s2 -- benchmark plan --> s5
s8 -- benchmark plan --> s9

この2つは depth が異なっていても問題ない。Plan の source-of-truth は input_state_ids である。

Storage 互換

既存 storage には state row に depth が含まれている。移行期は読み込み互換のために depth を読んでもよいが、新規保存では source-of-truth として扱わない。

移行案:

load 時は既存 depth を無視して DAG を復元する。

表示で必要な depth は DAG から再計算する。

互換のため一時的に保存してもよいが、仕様上は deprecated とする。

最終的には node_depths / nodes_by_depth / state row の depth を削除する。

不変条件

1. DAG records are append-only

State / Plan / Transition は基本的に削除・上書きしない。誤った探索や古い案も、探索履歴として残す。

2. Cursor is mutable

Cursor は現在どの State を見ているかを表す可変ポインタである。rollback, move, switch などは DAG を変更せず Cursor を移動する操作として扱う。

3. Plan must resolve cursors into state IDs

Plan を Cursor から作る場合、Plan には Cursor ID だけでなく、その時点で Cursor が指していた State ID を固定保存する。

Cursor は後から動くため、Plan が Cursor ID だけに依存してはいけない。

4. Single-source and multi-source plans are both valid

Plan は1つの State から作ってもよいし、複数 State を入力として作ってもよい。

1つの State から作る通常の plan は、input_state_ids が1つだけの multi-source plan と見なす。

5. Primary state is optional but useful

複数 State から Plan を作る場合でも、多くの場合「主状態」が存在する。したがって Plan には primary_state_id を持たせる。

ただし、完全な synthesis / aggregate のように主状態が明確でない場合は None を許してもよい。

6. Rollback is cursor-local

rollback は Run 全体を巻き戻す操作ではない。指定した Cursor を、その Cursor の active path 上の祖先 State へ戻す操作である。

別枝の State へ移動する操作は rollback ではなく switch / move として扱う。

7. Prediction anchor follows cursor semantics

PredictionDAG を refresh する場合、どの Cursor を anchor として refresh したかを記録する。

PredictionDAG の root predicted state は、anchor Cursor が指していた observed State の snapshot を起点に作られる。

データモデル案

Actor

@dataclass(frozen=True)
class Actor:
    actor_id: str
    actor_type: Literal["human", "agent"]
    name: str
    status: Literal["active", "paused", "done", "abandoned"] = "active"
    metadata: dict[str, JSONValue] = field(default_factory=dict)

Cursor

@dataclass
class Cursor:
    cursor_id: str
    owner_actor_id: str
    current_state_id: str
    state_kind: Literal["observed", "predicted"]
    name: str
    purpose: str | None = None
    status: Literal["active", "paused", "done", "abandoned"] = "active"
    metadata: dict[str, JSONValue] = field(default_factory=dict)

state_kind を持たせることで、observed state 用 Cursor と predicted state 用 Cursor を同じ構造で扱える。実装を分けたい場合は、ObservedCursor と PredictionCursor に分けてもよいが、最初は1つの Cursor 型で十分である。

CursorEvent

最小実装では必須ではないが、後から監査や再現性が必要になるため、Cursor 移動履歴を記録するイベントを用意できる。

@dataclass(frozen=True)
class CursorEvent:
    event_id: str
    cursor_id: str
    event_type: Literal["create", "move", "rollback", "switch", "refresh"]
    from_state_id: str | None
    to_state_id: str
    actor_id: str | None = None
    reason: str | None = None
    metadata: dict[str, JSONValue] = field(default_factory=dict)

ExecutionPlan

既存の from_observed_state_id は互換性のために残してもよい。ただし新しい意味論では input_state_ids と primary_state_id を中心にする。

@dataclass(frozen=True)
class ExecutionPlan:
    plan_id: str
    plan_kind: Literal["execution"]
    action_type: ActionType
    intent: str

    input_state_ids: tuple[str, ...]
    primary_state_id: str | None = None
    source_cursor_ids: tuple[str, ...] = ()

    from_observed_state_id: str | None = None  # compatibility alias

    inputs: dict[str, JSONValue] = field(default_factory=dict)
    safety_policy: dict[str, JSONValue] = field(default_factory=dict)
    assumptions: tuple[str, ...] = ()
    status: PlanStatus = "active"
    metadata: dict[str, JSONValue] = field(default_factory=dict)

互換ルールとして、from_observed_state_id は primary_state_id と同じ値、または input_state_ids[0] と同じ値にする。

PredictionPlan

PredictionPlan も同様に、複数 predicted state から未来 plan を作れるようにする。

@dataclass(frozen=True)
class PredictionPlan:
    plan_id: str
    plan_kind: Literal["prediction"]
    action_type: ActionType
    intent: str

    input_state_ids: tuple[str, ...]
    primary_state_id: str | None = None
    source_cursor_ids: tuple[str, ...] = ()

    from_predicted_state_id: str | None = None  # compatibility alias

    inputs: dict[str, JSONValue] = field(default_factory=dict)
    safety_policy: dict[str, JSONValue] = field(default_factory=dict)
    assumptions: tuple[str, ...] = ()
    confidence: float | None = None
    status: PlanStatus = "active"
    metadata: dict[str, JSONValue] = field(default_factory=dict)

RunHandle

@dataclass
class RunHandle:
    run_id: str
    requirement: Requirement
    trace_dag: TraceDAG
    prediction_dag: PredictionDAG

    actors: dict[str, Actor]
    cursors: dict[str, Cursor]

    current_observed_state_id: str | None = None  # deprecated compatibility
    _counters: dict[str, int] = field(default_factory=dict)

current_observed_state_id は将来的に削除候補だが、当面は main Cursor と同期させる。

Cursor 操作 API

create_actor

create_actor(actor_type: str, name: str, *, actor_id: str | None = None) -> Actor

Actor を作成する。人間ユーザーやサブエージェントを登録するために使う。

create_cursor

create_cursor(
    owner_actor_id: str,
    name: str,
    state_id: str | None = None,
    state_kind: Literal["observed", "predicted"] = "observed",
    purpose: str | None = None,
) -> Cursor

Cursor を作成する。state_id が省略された場合は、observed Cursor なら main の observed state、predicted Cursor なら現在の PredictionDAG root を使う。

move_cursor

move_cursor(cursor_id: str, to_state_id: str, *, reason: str | None = None) -> Cursor

Cursor を任意の State へ移動する。別枝への移動も許可する。

rollback_cursor

rollback_cursor(cursor_id: str, to_state_id: str, *, reason: str | None = None) -> Cursor

Cursor を active path 上の祖先 State へ戻す。to_state_id が祖先でない場合はエラーにする。

resolve_cursor_state_ids

resolve_cursor_state_ids(cursor_ids: list[str]) -> tuple[str, ...]

Cursor ID 群を、その時点で指している State ID 群へ解決する。

Plan 作成 API

plan_from_cursors

plan_from_cursors(
    cursor_ids: list[str],
    *,
    primary_cursor_id: str | None = None,
    planner: str | None = None,
    max_plans: int | None = None,
    action_type: str = "analysis",
    intent: str | None = None,
    inputs: dict[str, JSONValue] | None = None,
) -> list[ExecutionPlan]

Observed Cursor から ExecutionPlan を作る。内部で Cursor を State ID に解決し、source_cursor_ids, input_state_ids, primary_state_id を保存する。

extend_from_cursors

extend_from_cursors(
    cursor_ids: list[str],
    *,
    primary_cursor_id: str | None = None,
    planner: str | None = None,
    max_plans: int | None = None,
    action_type: str = "analysis",
    intent: str | None = None,
    inputs: dict[str, JSONValue] | None = None,
) -> list[PredictionPlan]

Predicted Cursor から PredictionPlan を作る。複数の predicted state を材料にして未来候補を合成する場合に使う。

PredictionDAG 方針

PredictionDAG にも Cursor を適用する。

最初は次の二段階で進める。

Phase 1: Single PredictionDAG with cursor anchor

Run に1つの PredictionDAG を残す。ただし PredictionDAG の manifest / metadata に次を保存する。

anchor_cursor_id: str | None
anchor_observed_state_id: str

refresh(cursor_id="main") を呼ぶと、指定 Cursor の observed state を anchor として PredictionDAG を作り直す。

Phase 2: Multiple PredictionDAGs

必要になったら、Cursor ごとに PredictionDAG を持てるようにする。

prediction_dags: dict[str, PredictionDAG]
prediction_dag_by_cursor: dict[str, str]

たとえば、agent A と agent B が別々の未来予測を持つ場合、それぞれが別の PredictionDAG を持てる。

CLI 仕様案

cursor list

optagent cursor list

Run 内の Cursor を一覧表示する。

cursor create

optagent cursor create main --actor human_takumi --state s_obs_0000
optagent cursor create agent-a --actor agent_a --state s_obs_0003 --purpose "explore kernel variant A"

cursor move

optagent cursor move main --to-state s_obs_0005

cursor rollback

optagent cursor rollback main --to-state s_obs_0002

plan create

単一 Cursor から作る。

optagent plan create --cursor main --intent "run benchmark"

複数 Cursor から作る。

optagent plan create \
  --cursor agent-a \
  --cursor agent-b \
  --primary-cursor agent-a \
  --intent "combine implementation A with analysis B"

--cursor が省略された場合は main を使う。

既存互換として、--state-id も残す。ただし新仕様では --cursor を推奨する。

extend create

Predicted Cursor から PredictionPlan を作る。

optagent extend create --cursor future-main --intent "consider likely benchmark outcomes"

複数 predicted Cursor から作る。

optagent extend create \
  --cursor future-a \
  --cursor future-b \
  --primary-cursor future-a \
  --intent "synthesize predicted outcomes"

refresh

optagent refresh --cursor main

指定 Cursor の observed state を anchor として PredictionDAG を refresh する。

移行計画

Step 0: 既存 single-current モデルに rollback CLI を追加し、depth 依存を外す

Cursor / Actor を追加する前に、まず現行の current_observed_state_id ベースの Run に対して rollback 操作を実装する。

同時に、TraceDAG / PredictionDAG の正しさ判定から depth 依存を外す。rollback は depth 比較ではなく ancestor 判定で実装する。DAG 本体に保存された node_depths / nodes_by_depth は段階的に derived index 扱いへ移行する。

この段階では Cursor はまだ導入しない。rollback は Run の current_observed_state_id を、TraceDAG 上の ancestor observed state に戻す操作として定義する。

重要なのは、rollback が TraceDAG の node / transition / plan / result を削除しないことである。TraceDAG は append-only の事実ログとして保持し、rollback は現在位置だけを移動する。

CLI 例:

optagent rollback --to-state s_obs_0002

または手数指定:

optagent rollback --steps 2

内部処理:

rollback(to_state_id):
    assert to_state_id is observed state
    assert to_state_id is ancestor of current_observed_state_id
    current_observed_state_id = to_state_id
    refresh(from_state_id=to_state_id)

この rollback は、後に Cursor を導入したとき rollback_cursor("main", to_state_id) へ自然に移行する。

Step 1: Schema 追加

Actor, Cursor, 必要なら CursorEvent を追加する。

Step 2: RunHandle に actors / cursors を追加

Run 初期化時に、デフォルト human Actor と main Cursor を作る。

Step 3: current_observed_state_id 互換レイヤー

既存コードの互換性のため、当面は current_observed_state_id を残す。ただし内部では main Cursor と同期させる。

Step 4: Cursor API 追加

create_cursor, move_cursor, rollback_cursor, resolve_cursor_state_ids を追加する。

Step 5: Plan schema 拡張

ExecutionPlan / PredictionPlan に source_cursor_ids, input_state_ids, primary_state_id を追加する。既存の from_observed_state_id / from_predicted_state_id は互換 alias とする。

Step 6: plan / extend を cursor-first に変更

plan_from_cursors と extend_from_cursors を追加し、CLI のデフォルトを Cursor ベースにする。

Step 7: Storage 対応

JSONL storage に actors.jsonl, cursors.jsonl, optional cursor_events.jsonl を追加する。

既存 run を load する場合、actors / cursors が存在しなければ default actor と main cursor を自動生成する。

Step 8: CLI 追加

optagent cursor サブコマンドを追加する。

既存の plan --state-id は残しつつ、plan --cursor を推奨する。

Step 9: PredictionDAG refresh を cursor 対応

refresh(from_state_id=...) に加えて refresh(cursor_id=...) をサポートする。

Step 10: Tests

最低限、次をテストする。

init 時に default actor / main cursor が作られる

main cursor と current_observed_state_id が同期する

cursor を複数作れる

cursor を move できる

rollback_cursor は ancestor のみ許可する

plan_from_cursors は cursor を state id に解決して保存する

cursor が後で動いても plan の input_state_ids は変わらない

複数 cursor から1つの plan を作れる

predicted cursor から PredictionPlan を作れる

storage roundtrip で actors / cursors が保持される

未決定事項

Cursor と Workspace の名前

現時点では Cursor を採用する。ただし、将来的に selected states, notes, working set, task status などが増える場合は Workspace や AgentWorkspace へ拡張する可能性がある。

selected_state_ids を Cursor に持たせるか

複数 Cursor から Plan を作れるため、最小実装では Cursor 自体に selected state を持たせなくてもよい。ただし UI や対話的比較を考えると、将来的に selected_state_ids または pinned_state_ids を Cursor に追加してよい。

PredictionDAG を複数持つか

初期実装では Run に1つの PredictionDAG を維持する。必要になったら Cursor ごとに PredictionDAG を持つ。

Plan as node / Hyperedge 表現

複数 State から Plan を作ると、意味的には directed acyclic hypergraph に近い。ただし実装上は Plan を明示的な record とし、input_state_ids を持たせることで通常のデータモデルとして扱う。

最終的な一文

optimization-agent は、共有 append-only DAG の上に、複数 Actor が複数 Cursor を持ち、その Cursor 群を State ID に解決して Plan を生成する Multi-Actor Cursor Model へ移行する。

