# Direction

Arctx は v0.3.0b1 から DAG Core Redesign に入ります。

旧来の「仕様履歴を残すツール」という説明ではなく、今後は次の定義を中心にします。

```text
Arctx = one append-only DAG log
```

ユーザーが扱う基本モデル:

```text
Node(s) -- Step --> Node
Payload attaches to Node / Step
Cut is a Payload
```

## Phase 1

まず表現とCLIを新仕様へ寄せます。

- 外向きには `Step` ではなく `Step` と呼ぶ。
- `arctx add node` で依存を持たない Node を作れるようにする。
- `arctx add step` で Node から Step を作り、出力 Node を自動生成する。
- `arctx attach <id>` で Node / Step に Payload を付ける。
- `arctx cut <id>` で CutPayload を付ける。
- `arctx show <id>` と `arctx log` で確認する。

この段階では内部実装の `Step`, `step_id`, `steps.jsonl`, `target_kind="step"` は残します。

## Phase 2

Phase 1 のCLIと用語が固まったら、内部実装も Step に寄せます。

候補:

- `Step` -> `Step`
- `step_id` -> `step_id`
- `StepPayload` -> `StepPayload`
- `target_kind="step"` -> `target_kind="step"`
- `steps` -> `steps`

この変更は storage schema、extension API、tests に広く影響するため、Phase 1 とは分けます。

詳細は以下を参照してください。

- `docs/ja/DAG_CORE_REDESIGN.md`
- `docs/ja/DAG_CORE_MIGRATION_PLAN.md`
