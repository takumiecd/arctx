# コンセプト

optagent は、最適化や問題解決の過程を「あとから読める構造」として保存するための基盤です。

単に最終成果だけを見るのではなく、次の情報を run の中に残します。

- どんな目的で始めたのか
- どの状態から、何を試そうとしたのか
- 実行前にどうなると予測したのか
- 実際には何が起きたのか
- どの試行や結果を無効化したのか
- どの地点から別の探索を始めたのか

## 中心にある考え方

optagent が構築しているのは、最適化プロセスのための append-only な履歴グラフです。

`RunGraph` は run 全体の DAG です。`Node` はある時点の状態を表し、`InputTransition` は「この状態から何を試すか」、`OutputTransition` は「その試行からどんな結果に到達したか」を表します。

`InputTransition` は複数の input node を受け付けます（multi-input / join）。これにより、複数の試行結果を合流させた次の探索ステップを表現できます。

`OutputTransition` が prediction か observed result かは、OT に付いている payload の種別で決まります。`PredictionPayload` が付いていれば predicted、`ResultPayload` が付いていれば observed です。observed / predicted という区別は OT 自体のフィールドには存在しません。`RunGraph.output_kind(ot_id)` でどちらかを判定できます。

意味のある情報は graph record に直接埋め込まず、payload として attach します。

- `PlanPayload`: 何を試すつもりだったか（InputTransition に付く）
- `PredictionPayload`: 実行前にどうなると見込んだか（OutputTransition に付く）
- `ResultPayload`: 実際に何が起きたか（OutputTransition に付く）
- `NotePayload`: 状態に対するメモ（Node に付く）
- `CutPayload`: 間違った試行や結果の無効化（InputTransition または OutputTransition に付く）

この分離によって、optagent は単なるログではなく、試行錯誤の構造を扱えます。

## CLI の位置づけ

CLI は `RunGraph` を操作するための薄いインターフェースです。

`init` で run を作り、`plan` で次の試行を追加し、`predict` で期待される結果を残し、`observe` で実測結果を保存します。`trace` や `show` は、保存された構造を読み返すために使います。

`dump` コマンドは run 全体を 1 発でレンダリングします。LLM への文脈渡しには `--format outline`、図として確認するには `--format mermaid` を使います。

基本の流れは次の通りです。

```text
init
  -> plan
  -> predict
  -> optagent の外で実行
  -> observe
  -> trace / show / dump
```

optagent は最適化を実行するものではありません。外部の人間、LLM、script、benchmark runner、executor が行った判断や結果を、共有可能な状態グラフとして残すためのものです。

## 何に向いているか

optagent は、途中経過に価値がある作業に向いています。

- コード最適化
- カーネル最適化
- ベンチマーク実験
- 調査や仮説検証
- LLM / script / executor が混ざる問題解決ループ

特に、同じ目的に対して複数の試行があり、予測と実測を対応づけたい場合に価値があります。

## 何ではないか

optagent は、現時点では次のものではありません。

- 汎用 chatbot framework
- LangChain 的な general agent framework
- benchmark 付き code generator
- executor を内蔵した自動最適化ツール
- 生成コードを自動で元ファイルに書き戻すツール

実行、評価、コード生成、ベンチマークは外側の system が担当します。optagent の役割は、それらが生み出す plan、prediction、result を構造化して保存することです。
