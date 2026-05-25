# Concept

stag は作業履歴を append-only な RunGraph として記録します。

グラフ骨格は小さく保ちます。

- `Node`: 作業履歴上の状態や地点。
- `Transition`: 1 つ以上の node から実行した作業。
- `Edge`: 接続だけ。`node -> transition` または `transition -> node`。

意味は payload に分離します。plan / prediction / result / note / cut / Git
change は、payload の種類で表します。

並列 agent は、それぞれ新しい node / transition / edge / payload / work event
の batch を append します。既存履歴は書き換えません。
