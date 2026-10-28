# Contributing to ARCTX

Thank you for your interest in ARCTX! This document covers how to get
started, where to ask questions, and what we look for in contributions.

## Quick Links

- **Issues & Bugs**: [GitHub Issues](https://github.com/takumiecd/arctx/issues)
- **Discussions**: [GitHub Discussions](https://github.com/takumiecd/arctx/discussions)
- **Beta Status**: 0.2.0b2 — the core graph model is stabilizing. Breaking
  changes are acceptable within the 0.2 series and will be documented in
  release notes.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/takumiecd/arctx.git
cd arctx

# Run without installing (packages are not usually installed during local dev)
PYTHONPATH=packages/arctx/src:packages/arctx-cli/src \
  python3 -m arctx_cli.main --help

# Run tests
PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=packages/arctx/src:packages/arctx-cli/src \
  python3 -m pytest packages/arctx/tests packages/arctx-cli/tests \
  --import-mode=importlib -q
```

## Project Layout

This is a monorepo with two independent packages plus a web frontend:

| Path | Import | Purpose |
|------|--------|---------|
| `packages/arctx/` | `import arctx` | Core API, storage, payloads, extensions |
| `packages/arctx-cli/` | `import arctx_cli` | `arctx` command — argparse CLI |
| `web/` | — | React frontend, served by `arctx web` and built into the `arctx` wheel |

Core (`arctx`) has **no CLI dependencies**; the CLI depends on core. The web
frontend imports neither: it consumes the `arctx export --format json`
document and, live, the `arctx serve` HTTP API.

## What to Contribute

### High Priority

- **Real-world examples**: Scripts in `examples/` that demonstrate how you
  use ARCTX. See `examples/benchmark_optimization.sh` and
  `examples/debugging_trace.sh` for the style we prefer.
- **Extension payloads**: Custom `PayloadBase` subclasses for your domain.
  We love seeing what people attach to the graph.
- **Bug reports**: Even rough reports help. Include:
  - `arctx --version` output
  - The command you ran
  - What you expected vs. what happened

### Medium Priority

- **Documentation translations**: We maintain Japanese and English docs in
  `docs/ja/` and `docs/en/`. Contributions in other languages are welcome.
- **Renderer improvements**: `arctx dump --format outline` and `--format
  mermaid` live in `packages/arctx/src/arctx/core/run/dump.py`.

### Not Looking For (Yet)

- Web UI / dashboard — out of scope for the core project. Build it as a
  separate package that consumes the core API!
- Alternative graph models — the `Node → Transition → Node` shape is
  canonical.

## Code Style

We use:

- **black** (`line-length = 100`)
- **ruff** for linting
- **mypy** with `disallow_untyped_defs = true`

Run before submitting:

```bash
ruff check packages/arctx/src packages/arctx-cli/src
black packages/arctx/src packages/arctx-cli/src
mypy packages/arctx/src packages/arctx-cli/src
```

## Pull Request Process

1. **Open an issue first** for non-trivial changes (new verbs, storage
   format changes, public API changes). This lets us align on direction
   before you invest time.
2. **Fork and branch** from `main`.
3. **Keep changes minimal**. ARCTX values simplicity — one idea per PR.
4. **Add tests** if you change core behavior. We use pytest.
5. **Update docs** if you change public API or CLI surface.
6. **Reference the issue** in your PR description.

## Commit Messages

We don't enforce a strict format, but please:

- Use the imperative mood (`Add feature`, not `Added feature`)
- Start with a module prefix when obvious (`docs:`, `cli:`, `core:`, `git:`)
- Explain the "why" in the body if the change is non-obvious

## 配布方針 / Distribution policy

2026-10-28 より PyPI へのリリースを休止します。既存の PyPI プロジェクト
（`arctx` / `arctx-cli`）は所有者が管理画面からアーカイブし、GitHub はソースの
参照・利用と個人開発のために残します。リリース・サポートの予定は保証しません。
アーカイブ後も PyPI の既存版はインストール可能です。

PyPI releases are paused. The owner handles PyPI archival separately; this
repository remains available for source use and personal development, without
a promised release or support schedule.

- GitHub Actions はテストとビルド確認のみで、公開ジョブはありません。
- `scripts/release.py` はローカルでのバージョン更新・ビルド・検査用です。
  `--upload` / `--repository` は削除済みで、引数解析時に拒否します。
- 両パッケージの `Private :: Do Not Upload` classifier は誤公開の防止用です。
  GitHub の公開状態やローカルインストールには影響しません。
- 再公開は所有者が明示的に判断した場合のみ行います。

現在のソースは Python 3.10 以上の仮想環境で、リポジトリのルートから入れます。

```bash
python -m pip install -e ./packages/arctx -e ./packages/arctx-cli
```

## Questions?

- For usage questions → [GitHub Discussions](https://github.com/takumiecd/arctx/discussions)
- For bug reports → [GitHub Issues](https://github.com/takumiecd/arctx/issues)
- For private/security concerns → DM the maintainer

## License

By contributing, you agree that your contributions will be licensed under
the MIT License.
