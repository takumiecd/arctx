# Agent Loop

推奨ループ:

1. `stag graph dump` で現在の文脈を読む。
2. `stag transition create --from NODE_ID --payload-type transition_payload --field type=suggestion --field proposal="..."` で方針を append。
3. 外部で作業する（実験・実装・コードレビューなど）。
4. `stag transition create --from NODE_ID --payload-type transition_payload --field type=implementation --field result="..."` で結果を append。
5. 間違った枝は削除せず `stag cut node NODE_ID` で無効化する。

fan-out（複数案の並列探索）は、同じ input node から `transition create` を複数回実行して作ります。
multi-input join は `--from N1 --from N2` で作れます。

並列 agent は新規 record だけを batch append します。merge は record-level
append であり、既存履歴の mutation ではありません。

## work session 固定モード

並列に作業するプロセスは、共有の `current.json` に依存せず、各プロセスの
環境変数で run と work session を固定します。

```bash
eval "$(stag work-session env --run run_xxx --new)"
stag transition create --from NODE_ID --payload-type transition_payload --field type=suggestion
```

sub process を起動する場合は `spawn` を使うと、子プロセスだけに一意な
`STAG_WORK_SESSION_ID` が渡ります。

```bash
stag work-session spawn --run run_xxx -- codex
stag work-session spawn --run run_xxx -- claude
```

毎回明示したい場合は、従来どおり `--run` と `--work-session` を渡します。

```bash
stag transition create --run run_xxx --work-session ws_xxx --from NODE_ID
```
