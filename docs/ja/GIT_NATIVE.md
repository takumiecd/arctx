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
  寿命が run dir の寿命と一致するため）。除外対象は `run.cache.pkl` /
  `.append.lock` / 一時ファイル。**除外してよいのは「消しても再生成できるもの」だけ**
  で、書き込み先を除外してはならない（この規則を破っていたのが `run.db*` = Phase 6 参照）
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

### Phase 4 実装で確定した詳細

**レコード**（`arctx.ext.git.payloads.GitChangePayload`）:

```
GitChangePayload(payload_id, target_id, branch, head_commit, commits=(), metadata={})
```

- `diff_summary` / `commit_log` フィールドは**削除**。`DiffSummary` /
  `CommitEntry` クラスも payload モジュールから消え、導出側の値型
  `arctx.core.gitref.DiffStat` / `CommitInfo` に移った
- `commits` は step が複数 commit にまたがる場合の全 SHA。`commit_shas`
  プロパティが `commits or (head_commit,)` を返す。`base_commit` は
  従来どおり `metadata` に置く（`base_commit` プロパティで読む）
- payloads モジュールは git 非依存のまま（asset と同じ規約）

**導出プラミング**（`arctx.core.gitref`、stdlib subprocess のみ）:
`commit_exists` / `commit_info` / `commit_infos` / `diff_stat` /
`changed_files` / `commit_patch`。いずれも `exclude` 引数で negative pathspec
を受け取る。

**導出層**（`arctx.ext.git.derive`）: `derive_git_change(payload, repo_root=None)`
→ `DerivedGitChange(available, note, commit_log, diff_stat, files)`、
`derive_patch(...)` → `(text, truncated, byte_count, note)`。**例外を投げない**:
解決できない参照は `available=False` と `note` で返す。

| 状態 | note |
| --- | --- |
| commit がこの clone に無い / `head_commit` が空 | `(commit not available locally)` |
| そもそも repo の外 | `(no git repository available here)` |

**`.arctx/**` の除外**: 導出する diff / file 一覧 / patch は run データを除外する
（`ARCTX_DATA_EXCLUDE`）。commit N の記録は commit N+1 に乗る仕様なので、
run データ自体は「レビュー対象の変更」ではない。上の「ノイズ対策 2」の実装。

**焼き込み patch の全廃**: `<run_dir>/artifacts/git/*.patch` と
`metadata["patch_artifact"]` は削除した。これを書いていた 2 つの writer
（`git finish` / `git add --commit`）はどちらも clean tree を要求し、
**commit 済みの** diff しか書いていなかったため、git が既にバイトを持っている。
未コミット変更の検証用に patch を焼いている箇所は存在しなかったので、
キャッシュとして残す必要もなかった。

**表示サーフェス**（すべて閲覧時導出）: `arctx git show --step`（record に
`derived` ブロックを添える）、`arctx git list --step`、`arctx show --step`、
TUI detail pane、web の `POST /web/ext/git/diff`（`branch` / `diff_stat` /
`available` / `note` を追加し、diff element は marker を描画する）。
`web/src/types.ts` に `RunGitChangePayload` / `GitChangeDiff` を同期済み。

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

### Phase 4 実装で確定した詳細

**`arctx explore` の 3 モード**（すべて `--json` 対応）:

| 形 | 出すもの |
| --- | --- |
| `arctx explore` | lane を 1 行ずつ。`* name  <summary 1 行>` / closed は `- ` |
| `arctx explore <LANE>` | purpose / 完全な summary / status / record 数 / frontier |
| `arctx explore --query "T1 T2"` | lane 名 + status、一致抜粋、飛べる id |

- 引数なしは **open を先**（`started_at` 順）、closed は
  `N closed lanes — use --all` の 1 行に畳む。`--all` で展開
- 1 行 summary は「最初の非空行を約 160 文字で切り詰め」
- 検索は空白区切りの語の **case-insensitive AND**。haystack は lane 名 +
  purpose + その lane が所有する全 payload。**opaque id は haystack に含めない**
  （抜粋が UUID だらけになるため。id を持っているなら `arctx show`）
- ランキングは「名前一致が先、次にラベル辞書順」。位置非依存で、
  current lane も `within_lane` も無い
- `LaneOverview` / `LaneSearchHit` の `to_dict()` に階層キーは一切無い
  （breadcrumb / ancestors / children / stale なし）

**current summary の意味論**: lane が所有する `SummaryPayload` のうち
`record_event_rank`（`WorkEvent.created_records` の append-only 台帳の順）で
**最後のものが勝つ**。jsonl 行順は union マージ後に信用できないため。

**core ヘルパ**（`arctx.core.lanes`）: `record_event_rank`、
`lane_summary_payloads` / `lane_current_summary`、`lane_purpose`、
`collapse_summary`、`lane_overview` / `list_lane_overviews`、`search_lanes`。
封印ブランチ `refactor/lane-dag-overview` の `search_lanes` / `lane_overview`
を移植ベースにし、階層を全て剥がした。

**書き込み側の補完**: `arctx lane create --purpose TEXT`（lane record の
metadata に入り、explore / guide が表示）と `arctx lane summarize <LANE>
--summary "..."`（lane を閉じずに current summary を更新する作業途中版）を追加。

**`arctx guide` の痩身**: 静的本文は「書き込みの 3 動詞」と「取得の 3 つの問い」
だけにし、`reparent` と `lane summarize` を明記、削除済みサーフェス
（lane 階層 / 独自 sync / コピー型 asset）への言及を全廃した。
`--context` は Run ID / Run Purpose / Current Lane（status・purpose・
current summary）/ Active Frontiers / 有効な extension を出す。祖先チェーンは
木が無いので出さない。暗黙の `default` lane は Lane record を持たないため
status 表示を省く。

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

### Phase 5 実装で確定した詳細

**lane サイドバー（`arctx explore` の GUI 版）**: `web/src/lanes.ts` は
`arctx.core.lanes` のフラットヘルパの TS 移植（`recordEventRank` /
`laneCurrentSummary` / `lanePurpose` / `collapseSummary` / `searchLanes`）。
open を先に 1 行 summary 付きで並べ、closed はトグルに畳む。lane 詳細は
purpose / status / 完全な current summary。**階層 UI は存在しない**。

**検索はクライアント側**: 検索の haystack（lane 名 + purpose + lane が所有する
payload、opaque id は除外）も AND セマンティクスも CLI と同じで、ロード済みの
run document だけで完結する（サーバ往復なし）。ヒットは lane + 抜粋 ＋
一致レコードへのジャンプ。

**asset 閲覧**: `AssetCard` が `GET /asset` で解決状態を取り、画像は
`/asset/content` の base64 を data URI で inline、テキストはプレビュー、tree は
`path`（asset 相対）で 1 階層ずつブラウズ。解決失敗は構造化ステータスをそのまま
表示。static/share モードは参照のみ（バイトは git にあるため）。
`arctx web` の `API_PATHS` に `/asset` `/asset/entries` `/asset/content` を追加した
（`/asset/raw` はバイナリ転送なので `arctx serve` 専用のまま）。

**git_change**: record からは branch / commits のみ、それ以外は
`POST /web/ext/git/diff` で導出。`arctx web` の git 拡張が custom element を
出す場合はそちらに譲る。

**削除**: コピー型 asset の URL 配管（`artifactSrc` / `artifactPath` /
`artifact://` / artifact scope context と `ScopedPayloads`）、単一タブ化していた
bulk records パネルのタブバー。

---

## Phase 6: SQLite バックエンドの削除（0.4.0b2）

`SqliteRunStore` と `arctx migrate --to sqlite` を削除した。理由は性能ではなく
**git-native と第二正典が両立しないから**である。

- `run.db` は `.arctx/.gitignore` で除外されていた。つまり backend を sqlite に
  すると、**書き込みは commit にも他のクローンにも届かない場所にだけ入り、
  git に載る jsonl は無言で凍る**。実測（382 node の実 run を複製して検証）:
  `migrate` 後に 1 step 書くと db 383 / jsonl 382 になり、jsonl 側からは
  `explore --query` で見つからない。
- `migrate` は `--to sqlite` の一方通行で、**db → jsonl に戻す経路が無かった**。
- `run.db` が無い状態で backend だけ sqlite にすると、`sqlite3.connect` が
  空ファイルを作るため**エラーにならず「0 lanes」と答える**（62 lane ある run で）。
- 得ていたもの: 同 run の load が cold 34.3ms → 20.8ms、warm（`run.cache.pkl`）
  12.2ms → 5.6ms。**14 ミリ秒**。しかも `run.db` 4.1M > `payloads.jsonl` 2.6M。

文書側は以前から「正典は jsonl のみ」「`run.db` は派生ファイル」と書いていたが、
実装はそう扱っていなかった（`SqliteRunStore` の docstring は "Store a run as..."、
`append_batch` は db に権威として書き、pkl キャッシュの整合チェックは
**db の行数に対して**行われ、jsonl と db を突き合わせる箇所は存在しなかった）。
文書の主張を実装に守らせる方向で解消した。

`ARCTX_STORE` と `config.json` の `storage.backend` は**読み続ける**。sqlite を
設定済みのマシンを黙って jsonl に切り替えると、その run.db の中身が忘れられる
だけなので、`RuntimeError` で「何が起きたか・データはどのファイルにあるか」を
告げる（`packages/arctx/tests/storage/test_backend_resolution.py`）。

**再導入しないこと。** 速度が要るなら派生キャッシュ（`run.cache.pkl` と同格＝
消しても安全・整合チェック付き・jsonl から再生成可能）として作ること。
書き込みを受け取るストアを増やしてはならない。
