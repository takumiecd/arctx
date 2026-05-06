# optagent

optagent は、コード最適化・カーネル最適化の試行を **証拠として残しながら進める**
ための最適化エージェント基盤です。

中心に置くのは、LLM や探索アルゴリズムではなく PredictionTree / EvidenceTree です。

```text
Requirement
  -> Attempt
      -> Hypothesis
      -> Action
      -> Artifact
      -> Observation
      -> Evidence
      -> Decision
      -> Finding
```

## 現在の正本ドキュメント

まず日本語版を正として固めています。

- [プロジェクトの方向性](docs/ja/DIRECTION.md)
- [状態モデル](docs/ja/STATE_MODEL.md)
- [エージェントの思考ループ](docs/ja/AGENT_LOOP.md)

古い設計メモや実験的な計画資料は [docs/archive/](docs/archive/README.md) に退避しています。

## 開発

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest tests -q
```

## License

MIT
