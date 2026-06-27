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

---

## 4. `arctx web` 用の拡張機能 (GUI の拡張)

`arctx web` は、ブラウザ側 (React GUI) の表示コードやカスタムルートをロードするための **Web 拡張機能** の仕組みを持っています。
これを利用して、独自の Payload 表示コード (Mermaid レンダラーや Git 差分ビューワなど) を GUI に注入できます。

### `WebExtension` プロトコルの実装

Python 側で `arctx.web.extensions.WebExtensionBase` を継承したクラスを作成します。

```python
# my_arctx_web_ext/extension.py
from arctx.web.extensions import WebExtensionBase, WebRoute, WebRequest

def my_custom_handler(req: WebRequest) -> tuple[int, dict]:
    # リクエストの処理 (JSON レスポンス)
    return 200, {"success": True, "data": req.body}

class MyWebExtension(WebExtensionBase):
    def scripts(self) -> list[str]:
        """ブラウザに挿入する JavaScript コードのスニペット。
        グローバル API `window.arctxWeb` を通じて、カスタムレンダラーを登録できます。
        """
        return [
            """
            if (window.arctxWeb) {
                window.arctxWeb.registerPayloadRenderer("my_payload_type", (payload) => {
                    return {
                        title: "マイカスタム表示",
                        summary: payload.content.title,
                        fields: [{ label: "データ", value: payload.content.val }]
                    };
                });
            }
            """
        ]

    def routes(self) -> list[WebRoute]:
        """この Web 拡張が提供するカスタム JSON API ルート"""
        return [
            WebRoute(method="POST", path="/web/myext/custom", handler=my_custom_handler)
        ]
```

### `pyproject.toml` への登録

Web 拡張をロードさせるには、`arctx_web.extensions` entry-point グループに登録します。

```toml
[project.entry-points."arctx_web.extensions"]
myext = "my_arctx_web_ext.extension:MyWebExtension"
```

---

## 5. コアと拡張の疎結合（デカップリング）の設計指針

拡張機能を実装するにあたって、**「arctx のコアコード (CLI / Web サーバーやフロントエンドの UI) は、特定の拡張機能に依存したロジックを直接持つべきではない」** という強い設計指針があります。

### ❌ 避けるべき実装方法 (密結合)
- CLI サーバー（`arctx serve`）のルーティングテーブルに `/assets/upload` のように、特定の拡張機能だけで使う特定のルートを直接登録する。
- React の UI コードの中に `attachPreset === "asset"` や `payload_type === "asset"` のような特定の拡張機能を前提としたフォームの定義やアタッチ処理を直接記述する。

### ⭕ 推奨される実装方法 (疎結合)
- サーバーコアは**汎用的なインターフェースのみ**を提供します。
  - 例：ファイル添付（画像や動画など）を扱いたい場合、特定の `asset` 拡張専用の API を作るのではなく、汎用的なアーティファクト保存 API である `POST /artifacts/upload` を提供します。
- 独自の UI や表示ロジックが必要な場合は、上記 `WebExtension.scripts()` を通じて、**拡張機能の側から動的に JavaScript をフロントエンドに注入**し、レンダラーを登録します。

---

## 6. 添付ファイル・メディアの扱い方（汎用的な方法）

ARCTX では、画像・動画・ドキュメントなどの添付ファイルは拡張機能に特別に依存したものではなく、**「アーティファクト」**として汎用的に扱われます。

### 1. ファイルのアップロードと保存場所
- API `POST /artifacts/upload` に Base64 形式でファイルを送信すると、現在起動している run の `artifacts/` ディレクトリ内に `art_<uuid>_<filename>` として物理的に保存され、以下のようなパスが返ってきます。
  - 返却パスの例：`artifacts/art_17df20b5_my_chart.png`

### 2. Markdown からの参照方法
アップロードされたファイルは、Markdown (Noteなど) から直接、相対パスまたは `/` 始まりの絶対パスのようにして参照することができます。これにより、GUI でのインライン描画や PDF 出力などが自然に機能します。

* **画像を表示する場合**
  ```markdown
  ![代替テキスト](/artifacts/art_17df20b5_my_chart.png)
  ```
* **動画をインラインで再生させる場合**
  ```markdown
  <video src="/artifacts/art_1234abcd_video.mp4" controls width="100%"></video>
  ```
* **ファイルをダウンロードリンクにする場合**
  ```markdown
  [ダウンロード](artifacts/art_5678efgh_document.pdf)
  ```

この仕組みにより、エクスポートされた Markdown ファイルなどを他者に共有した際にも、同じ `artifacts/` フォルダごと持ち運ぶだけで、パスが壊れずに再表示が可能です。
