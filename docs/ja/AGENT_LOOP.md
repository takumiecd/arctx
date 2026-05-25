# Agent Loop

推奨ループ:

1. `stag dump` で文脈を読む。
2. `stag plan` で intent を append。
3. 必要なら `stag predict` で予測を append。
4. 外部で作業する。
5. `stag observe` で結果を append。
6. 間違った枝は削除せず `stag cut` で無効化する。

並列 agent は新規 record だけを batch append します。merge は record-level
append であり、既存履歴の mutation ではありません。
