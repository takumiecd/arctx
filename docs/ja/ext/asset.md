# 添付ファイル・メディア (`asset`) — 標準ペイロード

`asset` は、画像、動画、PDF、テキストなどの外部ファイルを ARCTX 内で管理し、グラフのノード（Node）やステップ（Step）に添付（アタッチ）するための機能です。**拡張機能ではなく core 標準ペイロード**（`AssetPayload`）であり、有効化（`--extension`）は不要で常に利用できます。可視性（どのレコードから URL 参照できるか）が core の系譜判定（lineage）に依存するため、core に組み込まれています。

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

### 1. ファイルをアタッチする (`arctx asset attach`)

指定したファイルを active run の `artifacts/` ディレクトリにコピーし、アタッチされた `AssetPayload` を作成します。

```bash
# 特定のノードに画像を添付する
arctx asset attach path/to/my_photo.png --target n_abc123

# ステップにも添付できる
arctx asset attach path/to/report.pdf --target t_xyz789
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

Python コードからプログラム経由でファイルを添付する場合は、core verb `handle.attach_asset(...)` を使用します。

```python
from arctx import init
from arctx.core.schema.requirements import Requirement

handle = init(Requirement("req1", "task", "t"))

# 特定のノード (n_abc123) にファイルを添付する
payload = handle.attach_asset(
    "n_abc123",
    "path/to/chart.png",
)

# 添付したファイルのパス (artifacts/...) を取得
print(payload.path)
```

### 可視性（どこから参照できるか）

asset を結びつけた node/step **自身とその子孫（前方に辿れるレコード）**だけが、その asset を URL で参照できます。逆に言うと、あるレコードからは**自分と祖先**に付いた asset のみ参照可能です（兄弟・子孫の asset は参照不可）。あるレコードから参照可能な asset 一覧は `GET /assets/visible?from=<id>` で取得でき、判定ロジックは `arctx.core.lineage` に一本化されています。
