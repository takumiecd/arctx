# CLI

## 基本フロー

```bash
stag init req_demo --run-id demo
stag transition --run demo --inputs <root_node_id> --type experiment --content '{"lr":0.01}'
stag transition --run demo --inputs <n1_id> --type suggestion --max-outcomes 3
stag cut --run demo --node <node_id> --reason "不採用"
stag dump --run demo --format outline
stag dump --run demo --format mermaid
```

## コマンド一覧

- `stag init <req_id>` — 新規 run 作成
- `stag list` — run 一覧
- `stag transition` — Transition を作成する（`--inputs`, `--type`, `--content`, `--max-outcomes`）
- `stag cut --node NODE_ID` / `stag cut --transition T_ID` — CutPayload を append
- `stag show --run R --node N_ID` — record を JSON で表示
- `stag trace --run R --node N_ID` — 履歴を遡る
- `stag outcomes --run R --transition T_ID` — output node を確認
- `stag dump --run R [--format outline|mermaid]` — 全体を描画
- `stag view` — GraphView 管理
- `stag anchor` — scope anchor node を作成
- `stag git start/finish` — Git セッション操作
- `stag migrate` — jsonl → sqlite 変換
- `stag tui` — TUI を起動
- `stag current` / `stag use` — active run ポインタ管理

## 廃止コマンド

`stag plan`, `stag predict`, `stag observe`, `stag note` は削除済みです。
`stag transition` に統一しました。
