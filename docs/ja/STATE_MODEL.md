# State Model

`RunGraph` は次の append-only な辞書を保持します:

- `nodes`
- `steps`（公開サーフェス: steps）
- `payloads`
- `work_sessions`
- `work_events`

各 `Step` は `input_node_ids` と、ちょうど 1 つの `output_node_id` を保持します。
現行スキーマには永続化された `Edge` record はありません。

Payload のインデックスは target から導出されます: `payloads_by_node` と
`payloads_by_step`。

トポロジのインデックスは step の端点から導出されます:
`steps_by_input_node` と `step_by_output_node`。後者は **node → producing step の
list**（`dict[str, list[str]]`）。

## Producer の多重度と re-parent（append-only な付け替え）

1 つの `Step` の output は常に 1 node。ただし **1 つの node は複数の `Step` の
output になってよい**（append-only な re-parent のため）。構造上は多 producer を
許すが、**ポリシー不変条件として「1 node あたり active な producing step は高々
1つ」**を書き込み verb 側で保つ。これにより active なサブグラフは木のままで、
trace / lineage / lane / renderer は active producer を 1 つ辿るだけで済む。

- `RunGraph.producers_of(node)` — 全 producing step（active/inactive 問わず）
- `RunGraph.step_to_node(node)` — **active な** producer を1つ返す（無ければ None）
- `RunGraph.steps_to_node(node)` — 全 producer（消費側で inactive を除外）

活性計算（`cuts.py`）は次の不動点:

- Step は cut されている or **入力 node のいずれかが inactive** なら inactive
- Node は cut されている or **producing step を持ち、その全てが inactive** なら
  inactive（1つでも active な producer があれば node は生きる）

producer が 1 つの node ではこれは従来挙動に一致する（厳密な一般化）。

`RunHandle.reparent(node_id, new_input_node_ids, payload, ...)` は付け替えを 1 操作で
表す: 新 producing Step（`new_input_node_ids -> node_id`）を append し、それまで
active だった producer を cut する。誤って生成した node を、子孫を保持したまま
正しい lineage へ繋ぎ直せる。誤った lineage は削除されず inactive として残る。
new inputs は `node_id` と同一 lane に置く（lane-valid を保つため）。サイクル防止の
ため new input が `node_id` の子孫であってはならない。

## Lane membership

lane は append-only な `WorkEvent` から導出される「現在の所属」です。
run root node は lane 所属モデルの対象外です。run root 以外の node と全 step は
必ず 1 つの lane に所属している必要があります。

lane validation では step とその output node を 1 つの unit として扱います。
lane root は producer-less な lane node だけでなく、別 lane の input から入る
lane 内 entry step の output node でも構いません。ただし run root 自体を lane root
にすることはできません。

コア payload は汎用の `NodePayload` / `StepPayload` に加えて `CutPayload` です。
`CutPayload` は node または step を無効化する append-only な手段で、対象は
ストレージから削除されません。
`diagram` extension は図・モデル artifact 用の `DiagramPayload` を提供します。
中に持つ node/edge は対象 artifact の構造であり、ARCTX の `RunGraph` ではないため
循環していても構いません。
Git の状態は extension の状態です: `GitChangePayload`、branch payload、git の
work event は `arctx.ext.git` が登録します。

永続化は JSONL ストレージでは `nodes.jsonl`, `steps.jsonl`, `payloads.jsonl`,
`work_sessions.jsonl`, `work_events.jsonl` を、あるいは同等の SQLite テーブルを
使います。

`GraphView` / `views` は 0.3 beta の再設計で削除されました。既存の run には
古い `views.jsonl` が残る場合がありますが、新しいローダーはそれらをコアグラフへ
読み込みません。

## 整合性と append-only（設計方針）

> ここは現行実装ではなく、`CutPayload` を発展させるための設計の土台。
> 実装はまだ `CutPayload`（上記）。この節は移行先の基準を定義する。

### 原則: ストレージの append-only ≠ 意味の不変

レコードを一切書き換えなくても、子を持つ node に後から payload を attach したり
cut したりすると、*下流のレコードが前提にしていた「親の意味」が事後的に変わる*。
物理的には追記でも、論理的には書き換え（retroactive mutation）になりうる。
整合性を守るとは、この「事後の前提改変」と「取り消し不能な誤操作」を防ぐこと。

### 後付け attach の2分類

子の有無にかかわらず、attach は次の2種類に分類する。全面禁止ではなく、
*前提改変的なものだけ* を別機構に通す。

- **記述的・単調 (descriptive / monotonic)** — `SummaryPayload`,
  `NodePayload(type="note")`, `AssetPayload` など。下流の前提を崩さない。子は
  「生成時点の親」を前提に作られており、後から要約・メモ・asset が付いても子の
  妥当性は変わらない。→ 子があっても自由に attach してよい。
  `SummaryPayload` は core typed payload（`payload_type="summary"`, node-targeting）。
  注釈に過ぎないが、`trace(..., stop_at_summary=True)` が読み取り時にディスパッチ
  するため typed クラスにする（`CutPayload` / `AssetPayload` と同じ基準）。活性には
  一切影響しない点が `CutPayload` との違い。
- **前提改変的 (premise-altering)** — cut / verify-NG / invalidate など、下流の
  妥当性そのものを変えるもの。→ 自由な attach にはせず、可逆な状態イベント列に通す。

### 状態イベント列（前提改変的なものの置き場）

前提改変は対象ごとに順序付き append-only イベントとして記録し、読み取り時に
supersession（後勝ち）で現在状態へ投影する。

- 誤 cut は `uncut` イベントの**追記**で回復する。元の cut イベントは削除しない
  ＝append-only を守ったまま誤操作を救う。cut が何も削除しない現行設計のおかげで
  復活は無損失。
- 状態は単一 enum に畳まない。cut（構造）と verify（検証）は**直交軸**であり、
  同じイベント列に複数軸として載せる。`ACTIVE/CUT/VERIFIED/INVALIDATED` のような
  単一 enum への統合はしない。
- 基盤は既存の `WorkEvent`（順序付き・`created_at` 付き）に乗せられる。

### 2つの軸を分ける

cut による下流の inactive 化は、次の2つの違う問いを混同しないことで整合する。

- **生成時の妥当性** — 「この子は生成時点で妥当に作られたか」。**不変。永遠に true。**
  後から覆らない（歴史の整合性）。
- **現在の有効性** — 「この子は今アクティブか」。**現在ビューの投影。** 親が cut
  されれば inactive、`uncut` すれば復活する。

「整合性が崩れる」ように見えるのは現在ビューを歴史と誤読した場合。2軸を分ければ
cut しても歴史側は一切崩れない。
