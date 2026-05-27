---
name: arctx-extension-inproject
description: ARCTXを使うプロジェクト内にドメイン固有のペイロード型（と任意でバーブ）を追加する。別パッケージ不要。
---

# プロジェクト内カスタムペイロードの追加

サードパーティパッケージを作らずに、既存のプロジェクト内でARCTXのペイロード型を拡張する手順。

## 1. カスタムペイロードクラスを定義する

`PayloadBase` を継承し、`payload_type` を `field(default="...", init=False)` で宣言する。
このパターンは `GitChangePayload` や `BranchPayload` と同一。

```python
# myproject/arctx_payloads.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from arctx.core.schema.payloads import PayloadBase, register_payload_class
from arctx.core.types import JSONValue, to_jsonable


@dataclass(frozen=True)
class BenchmarkPayload(PayloadBase):
    """ベンチマーク結果をTransitionに記録するペイロード。"""

    payload_id: str
    target_id: str
    metric_name: str
    value: float
    unit: str
    baseline: float | None = None
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    # target_kind と payload_type は init=False で固定する
    target_kind: Literal["transition"] = field(default="transition", init=False)
    payload_type: str = field(default="benchmark", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


@dataclass(frozen=True)
class ExperimentNotePayload(PayloadBase):
    """実験メモをNodeに付けるペイロード（NodePayload の代替）。"""

    payload_id: str
    target_id: str
    hypothesis: str
    result: str | None = None
    metadata: dict[str, JSONValue] = field(default_factory=dict)

    target_kind: Literal["node"] = field(default="node", init=False)
    payload_type: str = field(default="experiment_note", init=False)

    def to_dict(self) -> dict[str, JSONValue]:
        return to_jsonable(self)  # type: ignore[return-value]


# モジュールのインポート時に登録する（必須）
register_payload_class(BenchmarkPayload)
register_payload_class(ExperimentNotePayload)
```

### 命名規則

- `payload_type` はプロジェクト固有のプレフィックスを付けると衝突を避けやすい（例: `"myproject_benchmark"`)
- `target_kind` が `"node"` なら `attach()` 対象、`"transition"` なら `transition()` や `payload add --transition` 対象

## 2. モジュールをアプリ初期化時にインポートする

`register_payload_class` はインポート時の副作用として実行される。
`payload_from_dict` が呼ばれる前（= ランのロード前）に必ずインポートされていること。

```python
# myproject/__init__.py  または  myproject/app.py
import myproject.arctx_payloads  # noqa: F401 — 登録の副作用のため
```

ARCTX の CLI 経由で使う場合は、CLIのエントリポイントか設定ファイルでインポートを保証する。
（プロジェクト内専用なら、別途CLIプラグインは不要）

## 3. Python API からアタッチする

```python
from arctx.core.store.jsonl import JsonlRunStore
from myproject.arctx_payloads import BenchmarkPayload, ExperimentNotePayload

store = JsonlRunStore()
handle = store.load_run(run_id)

# Transition に BenchmarkPayload をアタッチする
payload = BenchmarkPayload(
    payload_id=handle._next_id("pl"),
    target_id=transition_id,          # 既存の transition_id
    metric_name="throughput",
    value=1234.5,
    unit="samples/sec",
    baseline=980.0,
)
# TransitionPayload は handle.attach ではなく run_graph.attach_payload を使う
handle.run_graph.attach_payload(payload)
store.save_run(handle)

# Node に ExperimentNotePayload をアタッチする
note = ExperimentNotePayload(
    payload_id=handle._next_id("pl"),
    target_id=node_id,
    hypothesis="sparse ratio 90% で推論速度が 2x になる",
    result="1.8x 達成。メモリバウンドが支配的だった。",
)
handle.attach(node_id, note)
store.save_run(handle)
```

`handle.attach()` は `target_kind == "node"` のペイロード専用。
`target_kind == "transition"` のペイロードは `handle.run_graph.attach_payload()` を直接呼ぶ。

## 4. CLI からアタッチする（カスタムデコーダーなしの場合）

カスタムペイロードを `arctx payload add` 経由でアタッチするには、
CLIが起動する前にモジュールが読み込まれている必要がある。
プロジェクト内専用の場合はラッパースクリプト経由が簡単:

```bash
# wrapper.py
import myproject.arctx_payloads  # 登録を強制
import sys
from arctx.cli.main import main
sys.exit(main())
```

```bash
PYTHONPATH=src python3 wrapper.py payload add \
  --transition <transition_id> \
  --payload-type benchmark \
  --field metric_name=throughput \
  --field value=1234.5 \
  --field unit=samples/sec
```

## 5. 未知のペイロードタイプのフォールバック動作

登録されていない `payload_type` を持つレコードは、`payload_from_dict` が
`target_kind` に応じて汎用の `NodePayload` または `TransitionPayload` に変換する。
フィールドは `content` に収まる。CLIはクラッシュしない。

これは後方互換性の保証:
- カスタムペイロードが未登録の環境で古いデータを読んでも壊れない
- ただし型安全性は失われるため、本番ではインポートを確実に行う

## 6. カスタムデコーダーが必要なケース

ネストしたデータクラスを持つペイロード（`GitChangePayload` の `CommitEntry` のような）は
`to_jsonable` だけでは復元できない場合がある。その場合は `register_payload_decoder` も使う:

```python
from arctx.core.schema.payloads import register_payload_decoder

def _benchmark_from_dict(data):
    return BenchmarkPayload(
        payload_id=str(data["payload_id"]),
        target_id=str(data["target_id"]),
        metric_name=str(data["metric_name"]),
        value=float(data["value"]),
        unit=str(data["unit"]),
        baseline=float(data["baseline"]) if data.get("baseline") is not None else None,
        metadata=dict(data.get("metadata") or {}),
    )

register_payload_decoder("benchmark", _benchmark_from_dict)
```

デコーダーは `register_payload_class` より優先される。両方登録する場合、
デコーダーが実際の復元に使われ、クラス登録はメタデータ（スキーマ確認など）向け。
