# Agent Loop

推奨ループ:

1. `arctx graph dump` で現在の文脈を読む。
2. `arctx transition create --from NODE_ID --payload-type transition_payload --field type=suggestion --field proposal="..."` で方針を append。
3. 外部で作業する（実験・実装・コードレビューなど）。
4. `arctx transition create --from NODE_ID --payload-type transition_payload --field type=implementation --field result="..."` で結果を append。
5. 間違った枝は削除せず `arctx cut node NODE_ID` で無効化する。
6. 区切りで `arctx export --format md`（必要なら `--exclude-cut`）で成果物を出力する。

fan-out（複数案の並列探索）は、同じ input node から `transition create` を複数回実行して作ります。
multi-input join は `--from N1 --from N2` で作れます。

並列 agent は新規 record だけを batch append します。merge は record-level
append であり、既存履歴の mutation ではありません。

## work session 固定モード（複数 agent で同じ run を共有する）

codex と Claude Code のような複数の agent が同じ run へ**同時に**書き込んでも
安全です。CLI のミューテーションはロック付きの差分追記で直列化され、互いの
レコードを上書きしません。各 agent は開始時のスナップショットを見て書くため、
同時に伸ばした枝は共通の親から分岐した兄弟 transition（fan-out）になります。

並列に作業するプロセスは、共有の `current.json` に依存せず、各プロセスの
環境変数で run と work session を固定します。誰の作業かを区別するには
`--user`（または `ARCTX_USER_ID`）も agent ごとに設定してください。未設定だと
user=`user` / work_session=`default` に潰れて区別できなくなります。

```bash
eval "$(arctx work-session env --run run_xxx --new)"
arctx transition create --from NODE_ID --payload-type transition_payload --field type=suggestion
```

sub process を起動する場合は `spawn` を使うと、子プロセスだけに一意な
`ARCTX_WORK_SESSION_ID` が渡ります。

```bash
arctx work-session spawn --run run_xxx --user codex -- codex
arctx work-session spawn --run run_xxx --user claude-code -- claude
```

毎回明示したい場合は、従来どおり `--run` と `--work-session` を渡します。

```bash
arctx transition create --run run_xxx --work-session ws_xxx --from NODE_ID
```

> 同一マシン前提です。別マシンから NFS / クラウド同期フォルダ越しに同じ run
> ディレクトリを直接叩く構成はファイルロックが効かないため非対応で、マシンを
> またぐ場合は `arctx sync` を使ってください。

## 複数 repo を 1 つの run で扱う

run は git の上位にあり、複数 repo にまたがれる。各 repo を対応表に登録すれば、
どの repo の commit も同じ run の履歴に積まれる。

```bash
cd ~/dev/frontend && arctx init "機能X" --run-id run_x --extension git
arctx git init                              # frontend を登録
cd ~/dev/backend  && arctx git repo add --run run_x   # backend を同じ run に登録
```

- commit の tip 整合は `(repo_id, branch)` キー。別 repo の同名 branch（例: 両方
  `main`）は衝突しない。
- 1 端末で run_x を追いながら repo 間を移動するなら、repo ごとの `.arctx-id` に
  頼らず端末を固定すると楽: `eval "$(arctx use run_x --shell)"`（env が優先）。
- `arctx export` は対応表を Repos セクションに出す。`local_path` は既定で落ちる
  （共有事故防止）。`--include-local` で含める。
