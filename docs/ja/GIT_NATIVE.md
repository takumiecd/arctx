# ARCTX git-native 設計

2026-07-26 の設計議論で確定した方針。以後の実装はこのドキュメントを正とする。
ベータ（0.3.x）につき互換シム・旧スキーマ移行は作らない。

## 立ち位置

ARCTX は Obsidian 型のツールになる。**データはリポジトリの中にただのファイルとして
存在し、共有は git / GitHub に完全に委ねる。** arctx は記録と閲覧のためにローカルに
インストールするツールであり、同期機構を一切持たない。

- 独自 sync（`arctx/core/sync/`、`arctx_cli/commands/sync_cmd.py`）は**全削除**
- Doxygen 型の静的サイト書き出し（Pages 等）は**採用しない**。閲覧は `arctx-web` 一本
- clone した人は `pipx install arctx-web` → リポジトリ内で起動、で閲覧できる

## ストレージ: `.arctx/` をリポジトリに同梱

```
<repo>/.arctx/
  runs/<run_id>/
    run.json
    graph.json
    nodes.jsonl
    steps.jsonl
    payloads.jsonl
    lanes.jsonl
    lane_events.jsonl
```

- **リポジトリ内の正典は jsonl のみ。** sqlite / キャッシュはマージ不能なので
  リポジトリに入れない
- `arctx init` はデフォルトで in-repo にデータを作る。`ARCTX_HOME` 方式は廃止方向
- active run ポインタ（`<gitdir>/arctx-id`）は現行のまま（worktree ごとの現在 run）

### Phase 1 実装で確定した詳細

- **store dir の解決順**: (1) `ARCTX_HOME` 環境変数 → `<ARCTX_HOME>/runs`（テストや
  意図的に repo 外へ置くツール向けの明示オーバーライド）、(2) 内包する git repo →
  `<repo_root>/.arctx/runs`（既定）、(3) repo 外なら `$XDG_DATA_HOME/arctx/runs` /
  `~/.local/share/arctx/runs`。`resolve_arctx_home()` は run データではなく
  ユーザ設定 `config.json` の場所という意味に純化した
- **キャッシュの置き場所**: run dir 内に置いたまま、`arctx init` が生成する
  `.arctx/.gitignore` で除外する（run dir の中に閉じるほうが単純で、キャッシュの
  寿命が run dir の寿命と一致するため）。除外対象は `run.cache.pkl` / `run.db*` /
  `.append.lock` / 一時ファイル
- **重複の解決**: 同一 ID の重複行は**最初の 1 行が勝つ**。レコードは immutable
  なので重複行は同一内容であり、first/last の選択は結果に影響しない（行順非依存に
  なることだけが目的）
- **記録順の復元**: cut/uncut の supersession は「後の marker が勝つ」ため
  レコードの記録順に依存する。これは行順ではなく `WorkEvent.created_records`
  （append-only の台帳）から復元する。イベントを持たないレコード（user/lane を
  渡さないコア API 直叩き）はファイル順のまま先頭に置く

### マージ戦略: union マージ

データモデルが git マージと構造的に相性が良いことがこの設計の根拠：

- 全レコードは append-only（削除なし。cut すら追記マーカー）
- ID は opaque UUID（並行追記で衝突しない）
- DAG なので行の並び順に意味がない

よって `.gitattributes` に `*.jsonl merge=union` を指定するだけで
「ブランチ間マージ＝行の和集合」として正しくマージできる。

**ローダー側の要件**: union マージは稀に行の重複・順序入れ替えを起こすため、
jsonl ロードは「ID で冪等・順序非依存」であることをテストで保証する。

### run.json / graph.json

jsonl でないメタファイルは union マージできない。作成時に書いて以後不変とするか、
可変部分を jsonl 側（イベント）に寄せる。

## 自己言及ループ: 「1 コミット遅れ」を仕様とする

`.arctx/` が repo 内にあるため、「commit N を arctx に記録する」とその記録自体が
未コミット変更になる。amend で同一 commit に含めることは原理的に不可能
（hash が変わり記録が狂う）。

**commit N についての記録は commit N+1 に乗る。これを仕様として受け入れる。**
出来事の記録は出来事の後に書かれる、という自然な順序であり、append-only ＋
union マージの世界では記録がどの commit に乗るかは正しさに影響しない。

ノイズ対策：

1. `.gitattributes` に `.arctx/** linguist-generated=true`（GitHub の diff で折りたたみ）
2. GitChangePayload の diff 計算・`git verify` の clean 判定から `.arctx/` を除外
   （「arctx 的にはツリーはクリーン」の判定を一貫させる）

## Asset: git asset に一本化

コピー型 asset（`<run_dir>/artifacts/` への複製、`POST /artifacts/upload`）は**削除**。
asset は `(commit, path)` による git オブジェクトへの参照のみとする。

- 添付したいファイルは commit してから attach する（「見せたいなら commit しろ」）
- path はリポジトリルート相対。**ディレクトリも指せる**（git tree があるため）
- 読み出しは serve 層が `git show <commit>:<path>` / `git ls-tree` で解決
- clone すれば asset は自動的に「同期済み」— 独自 sync 削除と噛み合う
- 弱点: 参照先 commit がその clone に無い場合（push 忘れ・shallow clone）は
  壊れた参照になる。attach 時に警告する程度とし、完全保証はしない
- 巨大バイナリは git-lfs を README で案内（arctx 側では解決しない）

### Phase 3 実装で確定した詳細

**レコード**（`arctx.core.schema.payloads.AssetPayload`, `payload_type="asset"`）:

```
AssetPayload(payload_id, target_id, target_kind, commit, path, title=None, metadata={})
```

- 真実は `commit`（40 桁のフル SHA に正規化）と `path`（リポジトリルート相対、
  `""` はルートツリー）だけ。size / mime_type / content_hash は git から導出
  できるので**持たない**（「jsonl は事実、見た目は導出」）
- `target_kind` は `"node"` / `"step"` 両対応。repo フィールドは無い（absent = self）
- ペイロード定義自体は git 非依存。解決ヘルパは `arctx.core.gitref`
  （stdlib subprocess のみ。`arctx.paths` と同じくコア層で git を知る）

**verb**: `RunHandle.attach_asset(target_id, path, *, commit=None, target_kind=None,
title=None, repo_root=None, user_id=None, lane_id=None)`
（`arctx/core/run/asset.py`）

- `commit` 省略時は包含リポジトリの HEAD。指定時は `rev-parse --verify` でフル SHA 化
- attach 時に `git cat-file -t <commit>:<path>` で実在検証。blob / tree のみ許可し、
  解決しない参照は `MissingCommit` / `MissingPath` で**拒否**する
- リポジトリ外なら `GitRefError`（「asset は git オブジェクト参照なので repo が要る」）
- path は絶対 / cwd 相対 / repo 相対のいずれでも受け取り、repo 相対に正規化する
- 戻り値は `AssetAttachment(payload, warning, kind)`。`warning` は push 済み警告で、
  **レコードには焼かない**（push 状態は環境ローカルかつ時間で変わるため）

**push 済み警告のセマンティクス**（ブロックしない）:

| 状態 | 挙動 |
| --- | --- |
| remote が 1 つも無い | 警告「他人の clone では解決できない」 |
| `git branch -r --contains <commit>` が空 | 警告「push しないと壊れた参照になる」 |
| いずれかの remote-tracking ref に含まれる | 警告なし |

**CLI**:

```
arctx asset attach <TARGET_ID> <PATH> [--commit REF] [--title TEXT]
arctx asset show <PAYLOAD_ID>
```

`attach` は `attach` / `cut` と同じく target 種別を ID から自動判定する。警告は
stderr に `warning: ...` として出し、終了コードは 0。`show` は参照と、この clone で
解決するか（`found` / `missing_commit` / `missing_path` / `no_repository`）を出す。

**serve のエンドポイント形（安定契約）**:

| ルート | 返すもの |
| --- | --- |
| `GET /asset?payload_id=pl_x` | 参照 ＋ `resolution{status,kind,content_type}` |
| `GET /asset/entries?payload_id=pl_x[&path=sub]` | ツリーの直下エントリ一覧（JSON） |
| `GET /asset/content?payload_id=pl_x[&path=sub]` | ファイル内容（`encoding` が `utf-8` か `base64`） |
| `GET /asset/raw?payload_id=pl_x[&path=sub]` | ファイルの生バイト（HTTP シェルのみ） |

- `path` は**asset の path からの相対**。ディレクトリ asset を payload を増やさずに
  ブラウズするための引数で、`..` による脱出は 400 `bad_path` で拒否する
- 解決失敗は crash させず構造化エラー：`{"error": ..., "code": ...}` と
  404（`missing_commit` / `missing_path` / `unknown_payload` / `no_repository`）
  ないし 400（`not_a_blob` / `not_a_tree` / `not_an_asset` / `bad_path`）
- 二層構成は既存規約どおり。純関数は `arctx/serve/assets.py`（socket 非依存・単体
  テスト対象）、`arctx/serve/api.py` がルーティング、`/asset/raw` だけはバイナリ
  転送のため `http.server` シェルが同じ純関数を呼んで生バイトを返す
- 対象リポジトリは run データを包む repo（`find_repo_root(run_path)`）

`export --format json` は asset を他のペイロードと同様にそのまま出す（特別扱いなし）。
`web/src/types.ts` に `RunAssetPayload` / `AssetResolution` / `AssetTreeEntry` を同期済み。

## repo_id の廃止と「absent = self」規約

repo_id・repo registry・`RepoPayload`・`local_path` 除去処理は**全削除**。

**規約: repo 指定が無いレコードは、データを包んでいるリポジトリ自身を指す。**

将来複数 repo 連携を入れる場合は「外部 repo を指すときだけ repo 修飾子を付ける」
形で拡張する。この規約により、過去に記録された全データ（修飾子なし）は
自動的に自己参照として正しく解釈され、マイグレーション不要。
**ベータは単一 repo 完結を公式仕様とする。**

## GitChangePayload のスリム化

payload に持つ真実は commit hash（と branch）のみ。diff テキスト・commit log は
閲覧時に serve 層が git から導出する（手元に git の実体があるため）。
焼き込み済みテキストはキャッシュ扱いに格下げする。
「jsonl は事実、見た目は導出」を設計原則とする。

## Lane: フラット化（木の廃止）

lane は **git のブランチ相当のフラットな作業単位**。宣言的な親子関係は持たない。

- 保持: 名前 / purpose / status (open, closed) / close 時の必須 summary
- 削除: `lane link` / `lane unlink` / `lane adopt`、`parent_lane_id`、
  lane_linked/lane_unlinked イベント、overview の stale 検出、階層バリデーション

根拠: lane B の最初の Step は lane A のノードを入力に取って生まれるため、
「B は A から分岐した」は **DAG が既に記録している**。宣言的な木は二重帳簿であり、
帳簿の食い違いが 15 種のバリデーションを必要としていた。帳簿を DAG 一冊にすれば
検証ごと消える。階層ビューが必要なら読み取り時に DAG から導出する（表示側の仕事）。

### 構成的 membership（検証より構造）

- Step は「作成時の current lane」に属する
- 出力 Node は常にその Step の lane を継承する（独立 membership を持たない）

これにより membership の不整合が表現不可能になり、validate_lanes の大半が不要になる。

## 文脈取得: 検索が主役

エージェント／人間が必要とする問いは 3 つだけ：

1. **「いま何が起きているか」** → `arctx guide --context`：run の purpose ＋
   現 lane の詳細 ＋ active frontier。木が無いので祖先チェーンは不要
2. **「X について何が試されたか」** → `arctx explore --query`：検索一発。
   ヒット＝lane summary ＋ 一致抜粋 ＋ 飛べる ID。**降下は不要**（位置非依存）
3. **「ここで何が起きたか」** → `arctx dump --lane` / `arctx show`：狭域の詳細

`explore`（引数なし）はフラットな lane 一覧＋1 行 summary。lane が大量になったら
検索と closed の折りたたみで戦う（構造ではなく検索アルゴリズムに任せる）。

## 書き込みプロトコル: 3 動詞

エージェントの規約は「lane を開く → `add` する → summary 付きで close」に痩せさせる。

- `add` は現行のまま **Step＋出力 Node の一体作成**。standalone node は作らない
  （「producer なしノードは run root ただ一つ」の契約を守る。add_node 廃止の
  決定は 2026-06 から変わらず）
- ノードの繋ぎ直しは `reparent`（新 producer Step を追加し旧 producer を cut）で
  行う。CLI に一級コマンドとして出す
- payload は Node（状態の記録）と Step（遷移の記録）の両標的を維持する

## 実装フェーズ

1. **Phase 1 — in-repo ストレージ**: `.arctx/` レイアウト、`arctx init` の in-repo 化、
   `.gitattributes` 生成（union マージ + linguist-generated）、ローダーの
   冪等・順序非依存化とそのテスト
2. **Phase 2 — 削除**: `core/sync/` 一式、`sync_cmd`、コピー型 asset
   （artifacts/・upload API）、repo registry / `RepoPayload` / repo_id、
   lane link/adopt/stale/階層バリデーション
3. **Phase 3 — git asset**: `(commit, path)` 参照型 `AssetPayload`、serve 層の
   `git show` 解決、attach 時の push 済み警告
4. **Phase 4 — 取得系**: `explore` フラット一覧、`--query` 検索の磨き込み
   （旧ブランチ `refactor/lane-dag-overview` の `search_lanes` を移植ベースに）、
   `guide --context` 簡素化、GitChangePayload スリム化と閲覧時 diff 導出
5. **Phase 5 — web 追随**: types.ts 同期、lane 木 UI の撤去、asset 閲覧の git 解決
