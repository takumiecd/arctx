# Agent Loop

推奨ループ:

1. `stag dump` で現在の文脈を読む。
2. `stag transition --type suggestion --content '{"proposal":"..."}'` で方針を append。
3. 外部で作業する（実験・実装・コードレビューなど）。
4. `stag transition --type implementation --content '{"result":"..."}'` で結果を append。
5. 間違った枝は削除せず `stag cut --node NODE_ID` で無効化する。

fan-out（複数案の並列探索）は `--max-outcomes N` で作れます。
multi-input join は `--inputs N1 --inputs N2` で作れます。

並列 agent は新規 record だけを batch append します。merge は record-level
append であり、既存履歴の mutation ではありません。
