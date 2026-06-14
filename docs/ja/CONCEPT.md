# Concept

Arctx は、append-only な DAG を編集・整理・共有するための core layer です。

MVP の基本概念は 3 つです。

- `Node`: DAG 上の点。状態、成果物、判断、観測、設計断片などを表す。
- `Step`: 1 つ以上の Node から、新しい Node を生む操作。現行内部実装では `Transition` として保存される。
- `Payload`: Node / Step に付く意味情報。note、result、rationale、repo-ref、agent event、cut などを表す。

接続情報は Step が持ちます。独立した `Edge` record はありません。

```text
Node(s) -- Step --> Node
```

`CutPayload` は Payload の一種です。削除ではなく、対象 Node / Step とその下流を現在の有効 DAG から外す append-only marker です。

Phase 1 では、外向きのCLIとdocsでは `Step` と呼びますが、内部 class / storage には `Transition` という名前が残ります。内部名の全面変更は Phase 2 で扱います。
