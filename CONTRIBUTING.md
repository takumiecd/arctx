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
PYTHONPATH=packages/arctx/src:packages/arctx-cli/src:packages/arctx-tui/src \
  python3 -m arctx_cli.main --help

# Run tests
PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH=packages/arctx/src:packages/arctx-cli/src:packages/arctx-tui/src \
  python3 -m pytest packages/arctx/tests packages/arctx-cli/tests packages/arctx-tui/tests \
  --import-mode=importlib -q
```

## Project Layout

This is a monorepo with three independent packages:

| Path | Import | Purpose |
|------|--------|---------|
| `packages/arctx/` | `import arctx` | Core API, storage, payloads, extensions |
| `packages/arctx-cli/` | `import arctx_cli` | `arctx` command — argparse CLI |
| `packages/arctx-tui/` | `import arctx_tui` | `arctx-tui` command — Textual TUI |

Core (`arctx`) has **no CLI/TUI dependencies**. CLI and TUI depend on core
but not on each other.

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
ruff check packages/arctx/src packages/arctx-cli/src packages/arctx-tui/src
black packages/arctx/src packages/arctx-cli/src packages/arctx-tui/src
mypy packages/arctx/src packages/arctx-cli/src packages/arctx-tui/src
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

## Release Process

PyPI versions come from the package metadata, not from Git tags. Update the
version first, commit that change, then tag the release commit. Do not reuse a
version that has already been uploaded to PyPI.

Release automation lives in `scripts/release.py` and uses `uv`. The default
release surface is `arctx` plus `arctx-cli`; `arctx-tui` is secondary and is
excluded unless `--include-tui` is passed.

The standard release path builds the web GUI, copies `web/dist` into
`packages/arctx/src/arctx/web/static`, builds the selected packages into root
`dist/`, and runs `twine check`:

```bash
# Bump package versions, clear old dist files, build web/package artifacts,
# and validate the distributions.
uv run scripts/release.py 0.3.1b3 --prepare

# Review and commit the release bump.
git diff
git add packages/arctx/pyproject.toml \
  packages/arctx-cli/pyproject.toml \
  packages/arctx-tui/pyproject.toml \
  packages/arctx/src/arctx/__init__.py
git commit -m "release: prepare 0.3.1b3"

# Tag the commit that contains the matching pyproject.toml versions.
git tag -a v0.3.1b3 -m "Release v0.3.1b3"
git push origin main --tags

# Upload the validated distributions to TestPyPI first.
uv run scripts/release.py 0.3.1b3 --no-clean --upload --repository testpypi

# Then publish the same dist/ contents to PyPI.
uv run scripts/release.py 0.3.1b3 --no-clean --upload
```

To include the TUI package in the same release:

```bash
uv run scripts/release.py 0.3.1b3 --prepare --include-tui
```

## Questions?

- For usage questions → [GitHub Discussions](https://github.com/takumiecd/arctx/discussions)
- For bug reports → [GitHub Issues](https://github.com/takumiecd/arctx/issues)
- For private/security concerns → DM the maintainer

## License

By contributing, you agree that your contributions will be licensed under
the MIT License.
