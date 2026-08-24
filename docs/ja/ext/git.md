# Git 連携拡張機能 (`git`)

`git` 拡張機能は、**あなたが作ったコミット**を ARCTX の RunGraph に紐づけ、
その差分を読み取り時に git から導出するための拡張機能です。

**arctx は git を実行しませんし、git を監視もしません。** 以前あった
`arctx git commit` / `revert` / `merge` / `cherry-pick` / `reset` / `branch` /
`init` / `hook` / `worktree` はすべて削除しました。理由は 2 つです。

- arctx 自身の git サブプロセスが arctx 自身のフックを起動し、同じ操作が
  2 回記録されていました（run root に張り付いた幽霊 Step、同じ `head_commit`
  を主張する 2 つの Step、身に覚えのない `session_hook` レーン）。
- フック経由の取り込みは、`arctx add` がすでに追跡しているグラフ位置を
  推測し直していました。機構が 2 つあったので、ずれました。

記録は明示的です。**コミットは自分で作り、その sha を記録します。**

---

## 主な機能

1. **コミット参照の記録**:
   コミットハッシュとブランチ名だけを Step に Payload として記録します
   （`GitChangePayload`）。
2. **1 Run = 1 Repo**:
   run はデータを包むリポジトリ自身の中に存在し、git レコードは修飾子なしで
   その repo を指します（「absent = self」）。
3. **差分は導出、コピーしない**:
   diff stat・コミット subject・ファイル一覧・パッチ本文は、記録された sha を
   使って**読み取り時に git から**導出します（`arctx.ext.git.derive`）。
   clone にコミットが無ければ `available=false` と
   `(commit not available locally)` が返り、例外にはなりません。
4. **GUI での Diff プレビュー**:
   Web 画面上でシンタックスハイライト付きの差分を表示します。

---

## 使い方 (CLI)

### 1. run の作成と紐づけ

```bash
arctx init <req_id> --extension git
```

git repo 内なら `<gitdir>/arctx-id`（run ポインタ）も書きます。
**フックはインストールしません。**

### 2. コミットの記録

```bash
git commit -m "修正内容のサマリー"
arctx add --title "修正内容のサマリー" --type commit --commit HEAD
```

1 コマンドで Step と、その Step が指すコミットの両方を記録します。
レーン位置を追う機構は `arctx add` のもの **1 つだけ**です。
選んだノードから分岐するには `--from NODE` を渡します（fan-in には繰り返す）。

既存の Step にコミットを足すこともできます:

```bash
arctx git add --step <STEP_ID> --commit <SHA>
```

### 3. 読み返す

```bash
# Step に記録されたコミットと、いま git が報告する diff
arctx git show --step <STEP_ID>

# コミットハッシュだけ
arctx git list --step <STEP_ID>

# 全 step の descendant 制約を検査
arctx git verify
```

ブランチ・マージ・リバート・チェリーピックの**記録用コマンドはありません**。
git 側でその操作を行い、結果のコミットを `arctx add --commit` で記録してください。
マージのように複数の履歴が合流する場合は、`--from` を繰り返して
multi-input Step にします。

---

## Python API

`RunHandle` にマッピングされた `handle.git` ネームスペースは読み取り専用です。

```python
from arctx import init
from arctx.core.schema.requirements import Requirement

handle = init(Requirement("req1", "task", "t"))

handle.git.verify()                 # descendant 制約
handle.git.current_sha(step_id)     # その Step の最新 head_commit
handle.git.step_by_sha(sha)         # sha から Step を引く
```

コミットを記録するには `arctx.ext.git.helpers.attach.attach_commits_to_step`
を使います（CLI の `arctx add --commit` / `arctx git add` が呼んでいるもの）。
