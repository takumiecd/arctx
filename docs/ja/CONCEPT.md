# Concept

arctx は作業を append-only な RunGraph として記録します。

グラフの骨格は意図的に小さく保たれています:

- `Node`: 作業履歴上の状態、または地点。
- `Step`: 1 つ以上の入力 Node から、ちょうど 1 つの出力 Node への作業ステップ。

接続情報は `Step` 自身が持ちます (`input_node_ids` + `output_node_id`)。独立した
`Edge` record はありません。

意味は payload で付与します。同じ構造的な形が、payload の type に応じて
plan・prediction・result・note・cut・Git change を表現できます。

並列ワーカーは Node・Step・payload・work event のバッチを append します。
何も書き換えられません。
