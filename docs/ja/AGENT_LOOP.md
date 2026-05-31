# Agent Loop

## 推奨ループ

1. `arctx graph dump` で文脈を読む。
2. `arctx transition create --from NODE_ID --payload-type transition_payload --field type=suggestion --field proposal="..."` で方針を append する。
3. 実装、実験、レビュー、デバッグ、調査などの外部作業を行う。
4. `arctx transition create --from NODE_ID --payload-type transition_payload --field type=implementation --field result="..."` で結果を append する。
5. 間違った枝は削除せず、`arctx cut node NODE_ID` で無効化する。
6. 区切りで `arctx export --format md` を実行する。受け手に無効枝を見せない場合は
   `--exclude-cut` を付ける。

fan-out は、同じ input node から複数の transition を作って表現する。multi-input join は
`--from` を複数回渡す。

並列 process は、各 writer が新規 record だけを append すれば同じ run で作業できる。
merge は record-level append であり、既存履歴の mutation ではない。

## セットアップの考え方

ARCTX には別々の3種類の状態がある:

- **Run:** `<ARCTX_HOME>/runs/<run_id>` 配下の graph。
- **Repo pointer:** `<gitdir>/arctx-id`。`arctx init`, `arctx use`,
  `arctx git init`, `arctx git repo add` が書く。
- **Shell pointer:** `ARCTX_RUN_ID`。通常は
  `eval "$(arctx use <run_id> --shell)"` または `arctx work-session env` で設定する。

解決順:

```text
--run <id>
ARCTX_RUN_ID
<gitdir>/arctx-id
```

repo pointer は「この checkout は通常この run に属する」を表すときに使う。
shell pointer は、1つの端末で repo 間を移動しながら同じ run を追うとき、または
子 process を他の端末から分離したいときに使う。

## 1 repo + git

```bash
cd ~/dev/my-repo
arctx init "機能X" --run-id run_x --extension git
arctx git init
arctx git commit -m "first change"
```

`arctx init --extension git` は run を作成し git 連携を有効化する。
`arctx git init` は、その run に repo を明示登録し、repo marker と hooks を設定する。
以後、通常の `arctx git ...` コマンドは repo pointer から run を解決できる。

## 複数 repo を1つの run で扱う

run は git の上位にあり、複数 repo にまたがれる。各 repo を registry に登録すれば、
どの repo の commit も同じ run の履歴に積まれる。

```bash
cd ~/dev/frontend
arctx init "機能X" --run-id run_x --extension git
arctx git init

cd ~/dev/backend
arctx git repo add --run run_x
```

- commit tip 整合は `(repo_id, branch)` キーなので、別 repo の同名 branch
  （例: 2つの `main`）は衝突しない。
- 1つの端末で `run_x` を追いながら repo 間を移動するなら、repo pointer に頼らず
  端末を固定する: `eval "$(arctx use run_x --shell)"`。
- `arctx export` は登録 repo を Repos section に出す。`local_path` は
  machine-specific path の漏洩を避けるためデフォルトで落ちる。ローカル診断では
  `--include-local` を使う。

## Work Session 固定モード

並列 agent は、共有 repo pointer だけに頼らない。各 process の環境変数で run と
work session を固定する。

```bash
eval "$(arctx work-session env --run run_x --new --user codex)"
arctx transition create --from NODE_ID --payload-type transition_payload --field type=suggestion
```

子 process には `spawn` を使う。child には一意な `ARCTX_WORK_SESSION_ID` が渡り、
兄弟 terminal / 兄弟 child process と fixed session を共有しない。

```bash
arctx work-session spawn --run run_x --user codex -- codex
arctx work-session spawn --run run_x --user claude-code -- claude
```

毎回明示したい場合は、変更系コマンドに `--run` と `--work-session` の両方を渡す。

```bash
arctx transition create --run run_x --work-session ws_xxx --from NODE_ID
```

デフォルト attribution は `user=user`, `work_session=default`。誰が書いた record かを
区別したい場合は、agent ごとに `--user` または `ARCTX_USER_ID` を設定する。

この固定モードは、同一マシン上の複数 process を前提とする。NFS やクラウド同期
フォルダ越しに、複数マシンから同じ run directory を直接叩かない。マシンをまたぐ
交換には `arctx sync` を使う。

## Agent ごとの worktree

並列 coding agent では、work session と git worktree を組み合わせる。

```bash
arctx git worktree add ../my-repo-codex codex/run-x --base main
arctx work-session spawn --run run_x --user codex --worktree ../my-repo-codex -- codex
```

work session は worktree path を記録し、child に `ARCTX_GIT_WORKTREE=PATH` を export する。
git verbs は、shell cwd が別の場所でも、その worktree 内で実行される。
