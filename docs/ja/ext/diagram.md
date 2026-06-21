# ダイアグラム拡張機能 (`diagram`)

`diagram` 拡張機能は、Mermaid や Graphviz などの記述式テキストからダイアグラム（図・グラフ）を定義し、それを ARCTX のノードやステップに貼り付け（アタッチ）、GUI上でインタラクティブにプレビュー表示するための拡張機能です。

---

## 主な機能

1. **Mermaid / Graphviz のサポート**:
   `graph TD; A-->B` などのテキストデータを Payload（`DiagramPayload`）として保持します。
2. **GUI 上でのレンダリング**:
   Web 画面（GUI）上で、テキストから自動的にベクター画像（SVG）として図をレンダリングしてインライン表示します。
3. **ワークフローやアーキテクチャの視覚化**:
   実験のステップや推論プロセス、コンポーネント構成図などを RunGraph 内に明示的に残すことができます。

---

## 使い方 (GUI)

1. ノードまたはステップを選択し、**Attach Payload** パネルを開きます。
2. プリセットから **Diagram** を選択します。
3. 以下の項目を入力します。
   * **Title**: 図のタイトル（例: `システム構成図`）
   * **Format**: レンダリング形式（`mermaid` または `graphviz` を選択）
   * **Source Code**: ダイアグラムのソースコードを記述します。
     * 例 (Mermaid):
       ```mermaid
       graph TD
           A[データ収集] --> B(前処理)
           B --> C{判定}
           C -->|OK| D[学習]
           C -->|NG| E[再収集]
       ```
4. **attach payload** ボタンをクリックします。

アタッチされたペイロードは、詳細パネルでタイトル付きのきれいな図としてビジュアル表示されます。

---

## 使い方 (CLI)

CLI コマンド `arctx attach` などから直接 `diagram` タイプを指定して JSON データとしてアタッチすることも可能です。

```bash
# JSONファイル（diagram_spec.json）からダイアグラムをアタッチする例
arctx attach n_abc123 \
  --type diagram \
  --content '{
    "title": "Simple Pipeline",
    "format": "mermaid",
    "source": "graph LR; A-->B; B-->C;"
  }'
```
