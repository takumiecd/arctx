# コマンドログ拡張機能 (`command`)

`command` 拡張機能は、テストコマンドやスクリプトなどの外部コマンドを実行した際の、コマンドライン、作業ディレクトリ（Cwd）、実行時間（duration）、標準出力（stdout）、標準エラー出力（stderr）、および終了コード（exit code）を記録するための拡張機能です。

---

## 主な機能

1. **実行結果とログの永続化**:
   スクリプト実行やテストの成功・失敗の証跡ログを、ARCTX の RunGraph の一部（Payload）として永続化します。
2. **GUI での出力プレビュー**:
   アタッチされたコマンド実行結果の標準出力（stdout）や標準エラー出力（stderr）を、Web画面上で折りたたみ可能なログビューワー形式でプレビュー表示できます。

---

## 使い方 (GUI)

1. ペイロードをアタッチしたいノードまたはステップを選択し、**Attach Payload** パネルを開きます。
2. プリセットから **Command Run** を選択します。
3. 以下の各項目を入力します。
   * **Command**: 実行したコマンド名（例: `pytest tests/`）
   * **Exit Code**: 終了ステータスコード（正常終了なら `0`）
   * **Working Directory (Cwd)**: 実行したディレクトリパス
   * **Stdout**: 標準出力ログ
   * **Stderr**: エラーログ
4. **attach payload** ボタンをクリックします。

アタッチされたペイロードは、詳細パネルで「exit 0」などのステータスとともにログ表示されます。

---

## Python API

外部プログラムの実行ラッパーなどから自動的に記録する場合、Python API を使用するのが最も効果的です。`handle.command.run(...)` は **コマンドを内部で実行（`subprocess`）し、終了コード・標準出力・標準エラー・実行時間を自動的に取得** して新しい Step として記録します。stdout/stderr などを呼び出し側で用意して渡す必要はありません。

```python
from arctx import init
from arctx.core.schema.requirements import Requirement

handle = init(Requirement("req1", "task", "t"))

# コマンドを実行し、その結果（exit code / stdout / stderr / duration）を
# 新しい Step として自動記録する。
result = handle.command.run(
    command=["pytest", "packages/arctx/tests/core/test_run_api.py", "-q"],
    cwd=".",
    # 任意: 長い出力を切り詰める上限（デフォルト 20000 文字）
    max_output_chars=20000,
)

print(result)  # exit code・記録した step_id などを含む dict
```

> 主な引数: `command`（必須・リスト）、`cwd`、`user_id`、`work_session_id`、`max_output_chars`。
> 新しい Step はワークセッションの tip に追加されます（任意のノードへ後付けで attach するのではありません）。
