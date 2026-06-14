# CLI

この文書は v0.3.0b1 の DAG Core Redesign における主要CLIを説明します。

Phase 1 では、内部実装にはまだ `Transition` という名前が残ります。ただしユーザー向けCLIでは `Step` と呼びます。

## 基本フロー

```bash
arctx init demo --run-id demo

arctx add node --title "baseline" --run demo
arctx add step --from <node_id> --title "try cache" --run demo
arctx attach <node_or_step_id> --type note --field text="observed result" --run demo
arctx cut <node_or_step_id> --reason "invalid assumption" --run demo

arctx show <id> --run demo
arctx log --run demo
```

## 主要コマンド

MVP の主要CLIは以下です。

```bash
arctx init
arctx current
arctx use

arctx add node
arctx add step
arctx attach
arctx cut

arctx show
arctx log
```

`context`, `status`, `debug`, `sync`, `link` はMVPの主要CLIには入れません。

## current run の解決

多くの参照/変更コマンドは `--run` を受け取ります。省略した場合、ARCTX は対象 run を次の順で解決します。

```text
--run <id>            そのコマンドだけ
ARCTX_RUN_ID          current shell / process tree
<gitdir>/arctx-id     この git checkout の永続デフォルト
```

`arctx current` は repo pointer を表示します。

`arctx use <run_id>` は repo pointer を書きます。

`eval "$(arctx use <run_id> --shell)"` はファイルを書かず、この shell だけ `ARCTX_RUN_ID` を固定します。

## arctx add node

依存を持たない Node を作ります。

```bash
arctx add node --title "baseline"
arctx add node --type note --field text="initial observation"
```

`--title` や `--field` を渡した場合、Node に `NodePayload` が付きます。

Node は DAG 上の点です。状態、成果物、判断、観測、設計断片などを表します。

## arctx add step

入力 Node から Step を作り、出力 Node を自動生成します。

```bash
arctx add step --from n_123 --title "try new design"
arctx add step --from n_a --from n_b --title "merge results"
```

Step は現行内部実装の `Transition` に対応します。

```text
Node(s) -- Step --> Node
```

Phase 1 の出力では `kind: "step"` を返しますが、内部IDはまだ `t_...` です。

## arctx attach

Node / Step に Payload を付けます。

```bash
arctx attach n_123 --type note --field text="baseline"
arctx attach t_456 --type result --field score=0.91
```

`attach` は対象IDから Node / Step を自動判定します。

Phase 1 では Step は内部的に Transition なので、Step への Payload は内部では `target_kind="transition"` として保存されます。

## arctx cut

Node / Step に `CutPayload` を付けます。

```bash
arctx cut n_123 --reason "invalid assumption"
arctx cut t_456 --reason "bad derivation"
```

Cut は削除ではありません。append-only な Payload です。

互換形式も当面残ります。

```bash
arctx cut node <node_id>
arctx cut transition <transition_id>
arctx cut step <step_id>
```

## arctx show

Node / Step / Payload の 1 件を表示します。

```bash
arctx show n_123
arctx show t_456
arctx show pl_789
```

新形式では、内部 Transition は Step として表示します。

```json
{
  "kind": "step",
  "id": "t_...",
  "active": true,
  "step": {
    "kind": "step",
    "step_id": "t_...",
    "input_node_ids": ["n_..."],
    "output_node_id": "n_..."
  }
}
```

既存の詳細指定も互換のため残ります。

```bash
arctx show --node <node_id>
arctx show --transition <transition_id>
arctx show --payload <payload_id>
```

## arctx log

DAG の連なりを表示します。

```bash
arctx log
arctx log --from n_123
arctx log --to n_456
```

- `log`: root から下流を outline 表示する。
- `log --from`: 指定 Node から下流を outline 表示する。
- `log --to`: 指定 Node がどう作られたかを上流へたどる。

Phase 1 では既存の `dump` / `trace` 機能を利用しています。

## 旧CLIの扱い

以下はまだ残りますが、v0.3 系では主要CLIではなく compatibility / plumbing として扱います。

```bash
arctx transition create
arctx payload add
arctx graph dump
arctx node ...
```

内部実装の Step 化が進むまでは、これらを急に削除しません。

## Git 連携

Git 連携は標準 extension として残ります。

ただし v0.3 の中心は `arctx git commit` ではなく、DAG core の `Node / Step / Payload` です。

Git extension は、Git commit 情報を Step に付く Payload として扱う方向へ寄せます。

Phase 1 では既存の `arctx git ...` コマンドは維持します。

## Work Sessions

work session は、同じ run で並列作業する agent / terminal の attribution 単位です。

```bash
eval "$(arctx work-session env --run demo --new --user codex)"
```

新CLIも既存の `--user` / `--work-session` を受け取ります。

## Agent からの利用

Codex / Claude Code などの agent からは、まず `show` と `log` を組み合わせて現在の DAG を読む想定です。

```bash
arctx show <id>
arctx log --from <node_id>
arctx log --to <node_id>
```

将来的に `context` コマンドを追加する場合も、これは新しい基本操作ではなく、`show` と `log` を組み合わせた agent 向け合成ビューとして扱います。
