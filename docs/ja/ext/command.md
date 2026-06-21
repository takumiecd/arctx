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

外部プログラムの実行ラッパーなどから自動的に記録する場合、Python API を使用するのが最も効果的です。

```python
import subprocess
import time
from arctx import init
from arctx.core.schema.requirements import Requirement

handle = init(Requirement("req1", "task", "t"))

# 実行するコマンド
cmd = ["pytest", "packages/arctx/tests/core/test_run_api.py", "-q"]

start_time = time.time()
res = subprocess.run(cmd, capture_output=True, text=True)
duration_ms = int((time.time() - start_time) * 1000)

# コマンドの実行ログをノード (n_abc123) に記録する
handle.command.run(
    command=cmd,
    exit_code=res.returncode,
    cwd=".",
    stdout=res.stdout,
    stderr=res.stderr,
    duration_ms=duration_ms,
    target_id="n_abc123"
)
```
