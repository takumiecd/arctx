# Git 連携拡張機能 (`git`)

`git` 拡張機能は、開発プロセス中の Git コマンド操作（コミット、ブランチ操作、マージなど）を検出し、そのメタデータや差分（Diff）情報を ARCTX の RunGraph に紐付けるための拡張機能です。

---

## 主な機能

1. **Git コミットと履歴の自動追跡**:
   変更したコードのコミットハッシュや差分情報をステップに Payload として記録します。
2. **複数リポジトリの統合管理**:
   1つの run に対して複数の Git リポジトリを紐付け（`repo add`）、それぞれの履歴を並行して追跡できます。
3. **Git フックの統合**:
   `post-commit` や `post-rewrite` などの Git フックをインストールし、Git コマンドの実行時に自動的に ARCTX 側へ履歴を記録させることができます。
4. **GUI での Diff プレビュー**:
   アタッチされた Git コミット Payload の差分情報を、Web 画面上でシンタックスハイライト付きでプレビュー表示できます。

---

## 使い方 (CLI)

### 1. リポジトリの初期化とフック設定
現在のワーキングディレクトリの Git リポジトリを active run に登録し、自動追跡用の Git フックをインストールします。

```bash
arctx git init
```

### 2. コミット情報の記録 (`arctx git commit` / `arctx commit`)
現在の作業ツリーの変更点やコミット情報を、新しい Step / Payload として記録します。

```bash
# コミット情報を記録する (エイリアス arctx commit も利用可能)
arctx commit -m "修正内容のサマリー"
```

### 3. リポジトリ設定の管理
連携している Git リポジトリを管理します。

```bash
# 既存のリポジトリをこの run に登録する
arctx git repo add <slug> <local_path>

# 登録されているリポジトリの一覧を表示
arctx git repo list

# 特定のリポジトリの情報を表示
arctx git repo show <repo_id>
```

### 4. ブランチ操作の記録
ブランチの作成やマージ、リバート、チェリーピックなどの履歴を記録・追跡します。

```bash
# ブランチ情報を記録
arctx git branch <branch_name>

# 2つのブランチ履歴の合流 (マージ) を記録
arctx git merge --from <from_branch> --into <into_branch>

# リバートの記録
arctx git revert <commit_sha>
```

---

## Python API

Python コードから Git 拡張機能の機能（verbs）を呼び出すには、`RunHandle` にマッピングされた `handle.git` ネームスペースを使用します。

```python
from arctx import init
from arctx.core.schema.requirements import Requirement

handle = init(Requirement("req1", "task", "t"))

# Git コミットをアタッチする
handle.git.commit(
    message="Implement new feature",
    repo_id="repo_1",
    branch="main",
)
```
