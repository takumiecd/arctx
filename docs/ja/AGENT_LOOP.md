# Agent Loop

この文書は、Codex / Claude Code などの agent が v0.3.0b1 の DAG core CLI を使うときの基本ループを説明します。

Phase 1 では内部実装に `Step` が残りますが、agent 向けには `Step` として扱います。

## 推奨ループ

1. `arctx log` / `arctx show <id>` で現在の DAG を読む。
2. `arctx add step --from NODE_ID --title "..."` で次の作業単位を append する。
3. 必要な外部作業を行う。
4. `arctx attach <node_or_step_id> --type result --field ...` で結果や観測を付ける。
5. 間違った枝は削除せず、`arctx cut <node_or_step_id> --reason "..."` で無効化する。

基本形:

```bash
arctx log --run run_x
arctx show <id> --run run_x

arctx add step --from <node_id> --title "try parser rewrite" --run run_x
arctx attach <step_id> --type result --field status="works" --run run_x
arctx cut <node_or_step_id> --reason "invalid assumption" --run run_x
```

fan-out は、同じ input Node から複数の Step を作って表現します。

multi-input join は `--from` を複数回渡します。

```bash
arctx add step --from n_a --from n_b --title "merge findings" --run run_x
```

## 読み取り

agent はまず `show` と `log` を組み合わせます。

```bash
arctx show <id> --run run_x
arctx log --from <node_id> --run run_x
arctx log --to <node_id> --run run_x
```

- `show <id>`: Node / Step / Payload の 1 件を見る。
- `log --from`: 指定 Node から下流を見る。
- `log --to`: 指定 Node がどう作られたかを上流へたどる。

将来的に `context` を追加する場合も、これは `show` と `log` の agent 向け合成ビューとして扱います。

## 書き込み

新しい観測点や作業起点を作る場合:

```bash
arctx add node --title "baseline" --run run_x
```

既存 Node から新しい Step を作る場合:

```bash
arctx add step --from n_123 --title "try cache" --run run_x
```

Step の出力 Node は自動生成されます。

Node / Step に情報を付ける場合:

```bash
arctx attach n_123 --type note --field text="important assumption" --run run_x
arctx attach t_456 --type result --field elapsed_ms=120 --run run_x
```

Phase 1 では Step ID は内部都合で `t_...` のままです。

## Cut

Cut は削除ではありません。`CutPayload` を付ける append-only な操作です。

```bash
arctx cut t_456 --reason "slower than baseline" --run run_x
```

cut 済みの枝は read-time に inactive として扱われます。

## セットアップの考え方

ARCTX には別々の状態があります。

- **Run:** `<ARCTX_HOME>/runs/<run_id>` 配下の DAG。
- **Repo pointer:** `<gitdir>/arctx-id`。`arctx init`, `arctx use`, `arctx git init` などが書く。
- **Shell pointer:** `ARCTX_RUN_ID`。`eval "$(arctx use <run_id> --shell)"` や `arctx work-session env` で設定する。

解決順:

```text
--run <id>
ARCTX_RUN_ID
<gitdir>/arctx-id
```

## Work Session 固定モード

並列 agent は、共有 repo pointer だけに頼らず、各 process の環境変数で run と work session を固定します。

```bash
eval "$(arctx work-session env --run run_x --new --user codex)"
arctx add step --from <node_id> --title "codex attempt"
```

子 process には `spawn` を使えます。

```bash
arctx work-session spawn --run run_x --user codex -- codex
arctx work-session spawn --run run_x --user claude-code -- claude
```

毎回明示したい場合は、変更系コマンドに `--run` と `--work-session` の両方を渡します。

```bash
arctx add step --run run_x --work-session ws_xxx --from <node_id> --title "attempt"
```

デフォルト attribution は `user=user`, `work_session=default` です。誰が書いた record かを区別したい場合は、agent ごとに `--user` または `ARCTX_USER_ID` を設定します。

## Git / worktree

Git 連携は標準 extension として残りますが、v0.3 の中心は `arctx git commit` ではなく DAG core の Node / Step / Payload です。

並列 coding agent では、work session と git worktree を組み合わせられます。

```bash
arctx git worktree add ../my-repo-codex codex/run-x --base main
arctx work-session spawn --run run_x --user codex --worktree ../my-repo-codex -- codex
```

work session は worktree path を記録し、child に `ARCTX_GIT_WORKTREE=PATH` を export します。git verbs は、shell cwd が別の場所でも、その worktree 内で実行されます。
