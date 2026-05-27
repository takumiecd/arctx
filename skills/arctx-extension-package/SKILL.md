---
name: arctx-extension-package
description: ARCTXの拡張機能を独立したPythonパッケージとして作成・配布する。新CLIコマンドやRunHandleバーブの追加も含む。
---

# 配布可能なARCTX拡張パッケージの作成

`pip install` で配布できるサードパーティ拡張を作る手順。
リファレンス実装: `src/arctx/ext/git/` と `docs/ja/EXTENSION.md`。

## 1. パッケージレイアウト

```
my-arctx-ext/
├── pyproject.toml
├── src/
│   └── my_arctx_ext/
│       ├── __init__.py          # ExtensionBase サブクラスをエクスポート
│       ├── extension.py         # MyExtension クラス
│       ├── payloads.py          # PayloadBase サブクラス群 + 登録
│       └── verbs/
│           └── my_verb.py       # RunHandle バーブ実装
```

## 2. `ExtensionBase` を継承したクラスを定義する

```python
# src/my_arctx_ext/extension.py
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from arctx.ext.base import CliCommand, ExtensionBase, InitContext, Violation

if TYPE_CHECKING:
    from arctx.core.run.handle import RunHandle


@dataclass
class MyExtNamespace:
    """handle.myext.<verb>() の名前空間。"""

    handle: "RunHandle"

    def record_experiment(self, **kwargs: Any) -> object:
        from my_arctx_ext.verbs.experiment import record_experiment_impl
        return record_experiment_impl(self.handle, **kwargs)


class MyExtension(ExtensionBase):
    name = "myext"
    version = "0.1.0"

    def register_schema(self) -> None:
        """カスタムペイロードクラスを登録する。インポートの副作用で完了する。"""
        import my_arctx_ext.payloads  # noqa: F401

    def register_verbs(self, handle: "RunHandle") -> None:
        """handle.myext を設定する。二重登録を防ぐ。"""
        if hasattr(handle, self.name):
            return
        setattr(handle, self.name, MyExtNamespace(handle))

    def cli_commands(self) -> list[CliCommand]:
        """arctx myext <subcommand> を登録する。"""
        from my_arctx_ext.cli import add_parser, cli_myext
        return [CliCommand(name=self.name, add_parser=add_parser, handler=cli_myext)]

    def default_aliases(self) -> dict[str, str]:
        """arctx experiment -> arctx myext experiment のようなショートカット。"""
        return {
            "experiment": "myext experiment",
        }

    def register_init_options(self, parser: "argparse.ArgumentParser") -> None:
        """`arctx init --extension myext` に追加オプションを付ける。"""
        group = parser.add_argument_group("myext extension")
        group.add_argument(
            "--myext-workspace",
            dest="ext_myext_workspace",
            default=None,
            help="実験ワークスペースのディレクトリ",
        )

    def on_init(self, ctx: InitContext) -> None:
        """`arctx init --extension myext` 実行時の初期化処理。"""
        workspace = ctx.options.get("ext_myext_workspace")
        if workspace:
            # 例: ランディレクトリに設定ファイルを書き込む
            import json
            from pathlib import Path
            config_path = Path(ctx.run_dir) / "myext_config.json"
            config_path.write_text(json.dumps({"workspace": workspace}))

    def validate(self, handle: "RunHandle") -> list[Violation]:
        """整合性チェック。問題があれば Violation を返す。"""
        violations = []
        # 例: 未解決の実験がないか確認する
        return violations
```

## 3. ペイロードクラスを定義・登録する

`src/arctx/ext/git/payloads.py` と同じパターン:

```python
# src/my_arctx_ext/payloads.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from arctx.core.schema.payloads import (
    PayloadBase,
    register_payload_class,
    register_payload_decoder,
)
from arctx.core.types import JSONValue, to_jsonable


@dataclass(frozen=True)
class ExperimentPayload(PayloadBase):
    """実験の記録を Transition に付ける。"""

    payload_id: str
    target_id: str
    experiment_id: str
    config: dict[str, JSONValue] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: Literal["transition"] = field(default="transition", init=False)
    payload_type: str = field(default="myext_experiment", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


def _experiment_from_dict(data: dict[str, JSONValue]) -> ExperimentPayload:
    return ExperimentPayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        experiment_id=str(data.get("experiment_id", "")),
        config=dict(data.get("config") or {}),
        metrics={k: float(v) for k, v in (data.get("metrics") or {}).items()},
        metadata=dict(data.get("metadata") or {}),
    )


# インポート時の副作用として登録する
register_payload_class(ExperimentPayload)
register_payload_decoder("myext_experiment", _experiment_from_dict)
```

## 4. `pyproject.toml` でエントリポイントを登録する

```toml
[project]
name = "my-arctx-ext"
version = "0.1.0"
dependencies = ["arctx-api>=0.2"]

[project.entry-points."arctx.extensions"]
myext = "my_arctx_ext.extension:MyExtension"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

エントリポイントのキー（`myext`）は `ExtensionBase.name` と一致させる。
ARCTXは `importlib.metadata.entry_points(group="arctx.extensions")` でエクスポートされたクラスを発見する。

## 5. 拡張機能を有効化して使う

```bash
# インストール（開発中はeditable install）
pip install -e ./my-arctx-ext

# インストール済み拡張の一覧確認
PYTHONPATH=src python3 -m arctx_cli.main ext list

# 新しいランで拡張を有効化する
PYTHONPATH=src python3 -m arctx_cli.main init req_demo --extension myext

# 拡張バーブをCLIから使う
PYTHONPATH=src python3 -m arctx_cli.main myext experiment --from <node_id>

# alias が設定されていればショートカットで使える
PYTHONPATH=src python3 -m arctx_cli.main experiment --from <node_id>
```

既存ランに後から有効化する場合は `<ARCTX_HOME>/runs/<run_id>/extensions.json` を編集:

```json
{
  "enabled": [
    {"name": "myext", "version": "0.1.0"}
  ]
}
```

## 6. Python API から使う

```python
from arctx.core.store.jsonl import JsonlRunStore
from arctx.ext import attach_extensions

store = JsonlRunStore()
handle = store.load_run(run_id)

# 拡張のスキーマ登録とバーブ注入
attach_extensions(handle, ["myext"])

# handle.myext.<verb>() が使えるようになる
result = handle.myext.record_experiment(
    input_node_id=current_node,
    experiment_id="exp_001",
    config={"lr": 0.001, "batch_size": 32},
)
store.save_run(handle)
```

## 7. 実装上の注意点

**`Extension` Protocol vs `ExtensionBase`**
- `Extension` は `@runtime_checkable` な Protocol（メソッド定義のみ）
- `ExtensionBase` は全メソッドに空のデフォルト実装を持つ便利基底クラス
- 通常は `ExtensionBase` を継承し、必要なメソッドだけオーバーライドする

**`cli_commands()` の戻り値**
- `list[CliCommand]` を返す（`CliCommand` は `name`, `add_parser`, `handler` の3フィールドを持つ frozen dataclass）
- `add_parser(subparsers)` は `argparse.ArgumentParser` を返すこと
- `handler(args)` は終了コード `int` を返すこと

**`register_verbs` の二重登録防止**
- `if hasattr(handle, self.name): return` を入れる（`GitExtension` と同じパターン）

**`payload_type` の名前衝突を避ける**
- コアが予約する型: `node_payload`, `transition_payload`, `cut`, `join`
- git 拡張が予約する型: `git_change`, `branch`, `revert`, `cherry_pick`, `merge`
- 自拡張の型名にはプレフィックスを付ける（例: `myext_experiment`）

**`Violation` の返し方**
- `validate()` は問題がなければ `[]` を返す
- `Violation(extension=self.name, kind="missing_metric", message="...", details={...})` で構築する
