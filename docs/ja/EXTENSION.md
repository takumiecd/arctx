# STAG 拡張機能 (Extension) の作り方

STAGは `ExtensionBase` を継承した拡張クラスを定義し、Pythonの `entry_points` 機能を利用してパッケージングすることで、コアのコードを変更することなく機能を拡張できます。

## 1. 拡張クラスの作成

まず、`stag.ext.base.ExtensionBase` を継承して、拡張機能のクラスを作成します。

```python
# my_stag_ext/extension.py
from stag.ext.base import ExtensionBase, InitContext
from stag.core.run.handle import RunHandle

class MyExtension(ExtensionBase):
    name = "myext"
    version = "0.1.0"

    def register_schema(self) -> None:
        # 独自の Payload や WorkEvent などのスキーマを登録
        pass

    def register_verbs(self, handle: RunHandle) -> None:
        # Python API に機能を追加 (例: handle.myext.do_something())
        pass

    def register_cli(self, subparsers) -> None:
        # CLI サブコマンドを登録 (例: stag myext do-something)
        pass

    def default_aliases(self) -> dict[str, str]:
        # デフォルトのCLIエイリアス (例: stag do -> stag myext do-something)
        return {"do": "myext do-something"}

    def on_init(self, ctx: InitContext) -> None:
        # `stag init --extension myext` が実行された時の初期化処理
        pass
```

## 2. 外部からSTAGに認識させる方法 (entry_points)

自作した拡張機能をSTAGから自動で認識させるには、Python標準の `entry_points` を使用します。
パッケージ管理ツール（例: `pyproject.toml`）で、`stag.extensions` グループにクラスを登録してください。

### `pyproject.toml` の例

```toml
[project]
name = "my-stag-ext"
version = "0.1.0"
dependencies = [
    "stag>=0.1",
]

# STAG に拡張機能を登録
[project.entry-points."stag.extensions"]
myext = "my_stag_ext.extension:MyExtension"
```

※ 左辺 (`myext`) は拡張機能の名前、右辺 (`my_stag_ext.extension:MyExtension`) はロードするモジュールとクラス名です。

### インストールと確認

このパッケージをSTAGと同じPython環境にインストール（例: `pip install .`）するだけで、STAGが自動的に認識します。

```bash
# 認識されている拡張機能の一覧を確認
stag ext list

# 新しい run で拡張機能を有効化
stag init req_demo --extension myext
```

## 3. 既存の Run で有効化する

すでに作成済みの Run ディレクトリ (`<STAG_HOME>/runs/<uuid>/`) にある `extensions.json` ファイルを編集することで、後から有効化することも可能です。

```json
{
  "enabled": [
    {"name": "myext", "version": "0.1.0"}
  ]
}
```
