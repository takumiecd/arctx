# 添付ファイル・メディア拡張機能 (`asset`)

`asset` 拡張機能は、画像、動画、PDF、テキストなどの外部ファイルを ARCTX 内で管理し、グラフのノード（Node）やステップ（Step）に添付（アタッチ）するための機能です。

---

## 主な機能と設計指針

1. **ポータブルなアーティファクト保存**:
   添付されたファイルは、実行中の run ディレクトリ内にある `artifacts/` フォルダ（例: `runs/<run_id>/artifacts/`）にコピーされます。これにより、run ディレクトリごと持ち運ぶだけで添付ファイルが維持されます。
2. **コアとの疎結合 (Decoupled)**:
   API や GUI 側は特定の拡張（`asset`）にべったりと依存していません。標準機能である `/artifacts/upload` API を用いてファイルをアップロードし、Markdown 等から汎用パス（`/artifacts/art_...`）で参照する設計になっています。
3. **Markdown でのインライン表示**:
   添付した画像や動画は、Markdown 内の画像記法やビデオタグを用いることで、Web 画面上でそのままプレビュー表示できます。

---

## 使い方 (GUI - ブラウザ画面)

画面上の入力欄（Note や Custom JSON など）でファイルを添付する方法が最も簡単です。

1. ペイロード追加フォーム（例: **Note (Markdown)**）を開きます。
2. テキストエリアの下にある **「📎 Attach File」** ボタンをクリックします。
3. アップロードしたいファイルを選択します。
4. アップロードが完了すると、テキストエリアの末尾に以下のような Markdown 記法が自動で挿入されます。
   * 画像の場合: `![filename.png](/artifacts/art_<uuid>_filename.png)`
   * 画像以外の場合: `[filename.pdf](/artifacts/art_<uuid>_filename.pdf)`
5. 「attach payload」をクリックしてアタッチします。アタッチされたペイロードは、Markdown プレビュー機能により即座にインライン表示されます。

---

## 使い方 (CLI)

CLI コマンド `arctx asset` を用いて、ローカルファイルパスを指定してノードやステップに添付することができます。

### 1. ファイルをアタッチする (`arctx asset attach` / `arctx attach-file`)

指定したファイルを active run の `artifacts/` ディレクトリにコピーし、アタッチされた `AssetPayload` を作成します。

```bash
# 特定のノードに画像を添付する
arctx asset attach path/to/my_photo.png --target n_abc123

# エイリアス（ショートカット）も利用可能
arctx attach-file path/to/report.pdf --target t_xyz789
```

### 2. 添付ファイルの一覧を表示する
指定したノードまたはステップにアタッチされている `AssetPayload` の一覧を表示します。

```bash
arctx asset list --target n_abc123
```

### 3. アタッチ情報の詳細表示
特定の Payload ID を指定して、アタッチされたファイル名やファイルサイズ、相対パスなどのメタデータを JSON 形式で表示します。

```bash
arctx asset show pl_xyz456
```

---

## Python API

Python コードからプログラム経由でファイルを添付する場合は、`RunHandle` にマッピングされた `handle.asset` ネームスペースを使用します。

```python
from arctx import init
from arctx.core.schema.requirements import Requirement

handle = init(Requirement("req1", "task", "t"))

# 特定のノード (n_abc123) にファイルを添付する
payload = handle.asset.attach(
    target_id="n_abc123",
    file_path="path/to/chart.png",
)

# 添付したファイルのパス (artifacts/...) を取得
print(payload.path)
```
