# ARCTX

ARCTX は append-only な DAG を編集・整理・レビューするための core layer です。

v0.3.0b1 から、ARCTX は DAG Core Redesign に入ります。

旧来の「仕様履歴を残すツール」という説明ではなく、今後は次のモデルを中心にします。

```text
Arctx = one append-only DAG log
```

## パッケージ構成

| パッケージ | インストール | インポート | 用途 |
|-----------|------------|----------|------|
| `arctx` | `pip install arctx` | `import arctx` | コア API・ストレージ・拡張 |
| `arctx-cli` | `pip install arctx-cli` | `import arctx_cli` | `arctx` コマンド |
| `arctx-tui` | `pip install arctx-tui` | `import arctx_tui` | `arctx-tui` コマンド |

## 基本概念

MVP の基本概念は 3 つです。

- `Node`: DAG 上の点。状態、成果物、判断、観測、設計断片など。
- `Step`: 1 つ以上の Node から、新しい Node を生む操作。
- `Payload`: Node / Step に付く意味情報。

```text
Node(s) -- Step --> Node
Payload attaches to Node / Step
Cut is a Payload
```

`Cut` は独立した record ではなく、Payload の一種です。削除ではなく、対象と下流を現在の有効 DAG から外す marker として残ります。

## v0.3.0b1 の移行方針

Phase 1 では、外向きのCLIとdocsを `Node / Step / Payload` に寄せます。

内部実装にはまだ `Transition` という名前が残ります。

```text
外向き: Step
内部:   Transition
```

内部 class / storage / extension API まで `Step` に寄せる作業は Phase 2 で扱います。

詳細:

- [DAG Core Redesign](docs/ja/DAG_CORE_REDESIGN.md)
- [DAG Core Migration Plan](docs/ja/DAG_CORE_MIGRATION_PLAN.md)

## 30 秒で始める

```bash
pip install arctx-cli

arctx init demo --run-id demo
```

依存を持たない Node を作ります。

```bash
arctx add node --title "baseline" --run demo
```

Node から Step を作ります。Step は出力 Node を自動生成します。

```bash
arctx add step --from <node_id> --title "try cache" --run demo
```

Node / Step に Payload を付けます。

```bash
arctx attach <node_or_step_id> --type note --field text="observed result" --run demo
```

不要になった枝は CutPayload で無効化します。

```bash
arctx cut <node_or_step_id> --reason "invalid assumption" --run demo
```

DAG を確認します。

```bash
arctx show <id> --run demo
arctx log --run demo
arctx log --from <node_id> --run demo
arctx log --to <node_id> --run demo
```

## 主要CLI

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

`context`, `status`, `debug`, `sync`, `link` はMVPの主要CLIには入れていません。

## 旧CLIについて

以下は移行期間中の compatibility / plumbing として残ります。

```bash
arctx transition create
arctx payload add
arctx graph dump
arctx node ...
arctx view ...
arctx git ...
```

v0.3 系の主要な説明では、新しい `add node`, `add step`, `attach`, `cut`, `show`, `log` を優先します。

## Git 連携

Git 連携は標準 extension として残します。

ただし v0.3 の中心は Git commit ではなく、DAG core の Node / Step / Payload です。

Git commit 情報は、Step に付く Payload として扱う方向へ寄せます。

## Extension

Extension は引き続き重要です。

Core は小さく保ち、domain 固有の情報は Payload や extension validation として追加します。

Extension が担うもの:

- custom payload type
- custom validation
- custom CLI
- custom GUI panel
- repo integration
- agent integration
- import / export

## さらに読む

- [Concept](docs/ja/CONCEPT.md)
- [Direction](docs/ja/DIRECTION.md)
- [State Model](docs/ja/STATE_MODEL.md)
- [CLI](docs/ja/CLI.md)
- [Extension](docs/ja/EXTENSION.md)
- [Agent Loop](docs/ja/AGENT_LOOP.md)

English version: [README.md](README.md)
