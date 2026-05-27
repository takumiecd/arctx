# ARCTX 拡張機能 (Extension) の作り方

ARCTXは `ExtensionBase` を継承した拡張クラスを定義し、Pythonの `entry_points` 機能を利用してパッケージングすることで、コアのコードを変更することなく機能を拡張できます。

## 1. 拡張クラスの作成

まず、`arctx.ext.base.ExtensionBase` を継承して、拡張機能のクラスを作成します。

```python
# my_arctx_ext/extension.py
from arctx.ext.base import CliCommand, ExtensionBase, InitContext
from arctx.core.run.handle import RunHandle

class MyExtension(ExtensionBase):
    name = "myext"
    version = "0.1.0"

    def register_schema(self) -> None:
        # 独自の Payload や WorkEvent などのスキーマを登録
        pass

    def register_verbs(self, handle: RunHandle) -> None:
        # Python API に機能を追加 (例: handle.myext.do_something())
        pass

    def cli_commands(self) -> list["CliCommand"]:
        # CLI サブコマンドを登録 (例: arctx myext do-something)
        # 各要素は CliCommand(name, add_parser, handler)。
        # add_parser(subparsers) -> ArgumentParser、handler(args) -> int。
        return []

    def default_aliases(self) -> dict[str, str]:
        # デフォルトのCLIエイリアス (例: arctx do -> arctx myext do-something)
        return {"do": "myext do-something"}

    def on_init(self, ctx: InitContext) -> None:
        # `arctx init --extension myext` が実行された時の初期化処理
        pass
```

## 2. 外部からARCTXに認識させる方法 (entry_points)

自作した拡張機能をARCTXから自動で認識させるには、Python標準の `entry_points` を使用します。
パッケージ管理ツール（例: `pyproject.toml`）で、`arctx.extensions` グループにクラスを登録してください。

### `pyproject.toml` の例

```toml
[project]
name = "my-arctx-ext"
version = "0.1.0"
dependencies = [
    "arctx>=0.1",
]

# ARCTX に拡張機能を登録
[project.entry-points."arctx.extensions"]
myext = "my_arctx_ext.extension:MyExtension"
```

※ 左辺 (`myext`) は拡張機能の名前、右辺 (`my_arctx_ext.extension:MyExtension`) はロードするモジュールとクラス名です。

### インストールと確認

このパッケージをARCTXと同じPython環境にインストール（例: `pip install .`）するだけで、ARCTXが自動的に認識します。

```bash
# 認識されている拡張機能の一覧を確認
arctx ext list

# 新しい run で拡張機能を有効化
arctx init req_demo --extension myext
```

## 3. 既存の Run で有効化する

すでに作成済みの Run ディレクトリ (`<ARCTX_HOME>/runs/<uuid>/`) にある `extensions.json` ファイルを編集することで、後から有効化することも可能です。

```json
{
  "enabled": [
    {"name": "myext", "version": "0.1.0"}
  ]
}
```
