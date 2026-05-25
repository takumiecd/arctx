# Concept

stag は作業履歴を append-only な RunGraph として記録します。

グラフ骨格は小さく保ちます。

- `Node`: 作業履歴上の状態や地点。
- `Transition`: 1 つ以上の Node を入力として受け取り、必ず 1 つの Node を出力する作業単位。

`Edge` record は廃止済みです。接続情報は `Transition` 自身が持ちます。

意味は payload に分離します。

- `TransitionPayload(type="suggestion" | "implementation" | "analysis" | ...)` — Transition の意味
- `NodePayload(type="note" | ...)` — Node への注釈
- `CutPayload` — 無効化マーク（cascade で下流を inactive にする）
- `GitChangePayload` — Git commit 情報
- ユーザー定義 subclass — `PayloadBase` を継承して `register_payload_class()` で登録

並列 agent は、それぞれ新しい node / transition / payload / work event
の batch を append します。既存履歴は書き換えません。
