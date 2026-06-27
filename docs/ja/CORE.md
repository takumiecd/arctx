# ARCTX コアコマンド（基本これだけ）

日常はこの**5つの動詞**で足ります。残り（`log`/`dump`/`show`/`list`/`export`/
`use`/`serve`/`git` …）は閲覧・配管・拡張で、コアではありません。

| 動詞 | 役割 | 一言 |
|------|------|------|
| `init` | run を作る（1回） | 始点 |
| `lane` | 作業の**文脈**（ソロ/協働の作業の線） | どのレーンで作業するか |
| `add`  | node/step を作る＝**トポロジ**を伸ばす | グラフを育てる |
| `attach` | 既存 node/step に payload を足す＝**注釈** | 結果・計測・意図を貼る |
| `cut`  | 非活性化（理由付き）＝**却下/撤回** | 消さずに残す |

心象：**`init` で始め、`lane` で文脈を選び、`add`(構造)＋`attach`(注釈) で育て、
`cut` で撤回。** 失敗も過去も DAG に残る。

## 1. 始める

```bash
arctx init my_task --run-id scd-dev      # run を作成（<gitdir>/arctx-id に記録）
```

## 2. レーン（作業の文脈）— `source .venv` / `git switch` 風

```bash
arctx lane create geometry # レーン "geometry" を作成（切替はしない）
arctx lane switch geometry # 既存レーンに切替。typo ならエラー
arctx lane geometry        # switch の省略形。存在しない名前は作らない
                           # switch は <gitdir>/arctx-lane に記録 → シェルが変わっても同じ。eval 不要
arctx lane                 # 今どのレーンか表示
arctx lane list            # レーン一覧
arctx lane summaries geometry # レーン末端 node の summary（複数あり得る）を表示
arctx lane adopt geometry --history <tip> # 既存履歴をレーン所属として採用（作成履歴は書き換えない）
```

レーンは**1ユーザー専有ではない**：別の人が同じレーンに参加してよい（属性は各操作の
actor 単位）。**並行探索**を複数ターミナルで走らせるときだけ、シェルローカルに固定する：

```bash
eval "$(arctx lane switch geometry --shell)"  # この端末だけ env で固定（env はファイルより優先）
```

→ 普段は eval 不要（ファイルポインタが既定）。eval は**並行のときだけ**。

## 3. グラフを育てる

```bash
arctx add step --from <node> --title "explore ProductGeometry"   # 構造を伸ばす
arctx add step --from <A> --from <B> --title "merge A and B"      # 多入力 = 統合(join/merge)
arctx attach <node> --type result --json '{"recall@k":"rough at scale"}'  # 注釈を貼る
```

## 4. 却下（残す）

```bash
arctx cut --node <tip> --reason "grow-score not smooth at scale"  # 非活性化（理由付き、削除しない）
```

採用（merge）は **cut しないだけ**。続けるなら tip から `add` を重ねる。

## 5. 同期 = union（arctx ネイティブ）

```bash
arctx remote add origin <dir>   # remote 登録（v1 はファイル共有ログ）
arctx push                      # 相手に無い record を送る（ID差分・冪等）
arctx pull                      # 相手の record を取り込む＝union
```

統合は **ID-aware な union**（append-only・冪等・可換・収束）。git をお手本にしつつ
**git は流用しない**。CRDT なので **コンフリクト無し・履歴書き換え無し**。**手作業の
調停は無い** — 却下は cut として残るだけ。pull で record が入った後、target 所有者が
`accept`/`reject` する（PR は転送ではなく判断層）。

---

### PR の流れ（ゲート型・arctx ネイティブ）

PR は **DAG の中の append-only な審査状態**。提案は転送(push)ではなく、`proposal`
を貼ること。採用まで target の tip は進まない（＝pending）。

| やること | コマンド |
|---|---|
| ワークスペースを開く | `arctx lane switch <name>` |
| 提案（pending な PR を開く） | `arctx propose <source> --into <target>` |
| 未審査の提案を見る | `arctx propose --list` |
| レビュー | `arctx log` / `arctx dump` |
| 採用（整合性チェック付き統合） | `arctx accept <source>`（NGなら拒否→rebase 再提案） |
| 却下（残す） | `arctx reject <source> --reason ...`（＝cut） |
| 同期 | `arctx push` / `arctx pull`（remote は `arctx remote add`、union 収束） |

`accept` は内部で多入力 `add step`（join）を走らせ、土台が cut／サイクル／target が
前進していたら **拒否**（黙ってグラフを壊さない）。`reject` は `cut`。整合性の検査は
**accept 時に target に対して**行う — それが分散(remote/local)でも唯一正しい場所。
