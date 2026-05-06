# エージェントの思考ループ

## 基本思想

最適化エージェントは、単にコードを書いて benchmark を回す存在ではありません。
人間のエンジニアが行うように、調査し、原因を考え、仮説を立て、実装し、
検証し、結果から学ぶ存在です。

基本ループは次です。

```text
調査する
  -> 説明する
  -> 仮説を立てる
  -> 行動する
  -> 観測する
  -> 判断する
  -> 学習する
```

ここで重要なのは、**調査も action である** ということです。
調査は前処理ではありません。

例えば profile を取る、baseline matrix を回す、dispatch を trace する、
failure log を読む、といった行動はすべて「この情報を取れば不確実性が減るはず」
という予測を持った action です。

## 状態遷移として見る

エージェントは常に現在の状態を持ちます。

```text
State_t
  = requirement
  + current artifacts
  + observations
  + evidence
  + findings
  + open questions
  + predicted futures
```

action は、現在の状態をより良い次の状態に進めるために選ばれます。

```text
State_t -- Action_t --> Observation_t --> State_t+1
```

ここで「良い状態」とは、必ずしも速い candidate ができた状態だけではありません。

- 原因候補が絞れた
- 悪い枝を切れた
- 適用範囲を狭められた
- failure の説明ができた
- 次に取るべき action が明確になった
- 再利用可能な finding が残った

これらも良い状態遷移です。

## フェーズの変化

最適化の進み方は、常に同じではありません。
不確実性が減るにつれて、ループの形が変わります。

### 1. 不確実性が高い段階

最初は原因がわからないため、調査が多くなります。

```text
調査する
  -> 説明候補を作る
  -> 追加調査する
  -> 方向を決める
```

この段階では、実装よりも観測の設計が重要です。

例:

- まず baseline を shape ごとに測る
- correctness failure の種類を分ける
- dispatch が想定通りか確認する
- bottleneck が launch overhead か memory access か調べる

### 2. 方向が見えた段階

ある程度説明が立つと、候補実装を試し始めます。

```text
仮説を立てる
  -> 実装する
  -> test / benchmark する
  -> 判断する
  -> 学習する
```

この段階で重要なのは、単に速いかどうかではありません。

- どの scope で効くのか
- どの shape で regression するのか
- correctness risk は何か
- promotion できる証拠が揃っているか

を確認します。

### 3. 微調整段階

終盤では解の形が見えているため、調査は少なくなります。

```text
仮説を立てる
  -> 実装する
  -> 検証する
```

ただし、予測と違う結果が出た場合は、再び調査に戻ります。

## 予測とズレ

エージェントは、action を実行する前に期待する観測を持つべきです。

例:

```text
仮説:
  small batch は launch overhead が支配的である。

予測:
  fused dispatch を入れると small shape は速くなる。
  large shape は大きく変わらない。

観測:
  small shape は速くなった。
  large shape は遅くなった。

更新:
  candidate は small batch 用に scope を狭めるべき。
```

このズレは失敗ではなく、学習信号です。
だから `Decision` だけでなく `Finding` が必要です。

## 枝分かれ、枝刈り、合流

最適化は一本の直線ではありません。
複数の原因仮説や実装候補が枝分かれします。

```text
baseline
├── branch A: launch overhead hypothesis
│   ├── candidate A1
│   └── candidate A2
├── branch B: memory layout hypothesis
│   └── candidate B1
└── branch C: dispatch bug hypothesis
    └── investigation C1
```

証拠によって見込みのない枝は prune します。
別々の枝が同じ原因を説明している場合や、安全に組み合わせられる場合は merge します。

そのため、attempt には以下が必要です。

- parent attempt
- branch / lineage
- expected observation
- actual observation
- prediction error
- finding
- decision reason

## 実装上の含意

このモデルから、次の設計方針が出ます。

1. investigation action を first-class にする。
2. implementation action と verification action も同じ枠で扱う。
3. action には expected observation を持たせる。
4. observation と expected observation の差分を保存する。
5. failed attempt でも finding を残す。
6. state は現在の信念と open questions を持つ。
7. EvidenceTree は過去の immutable log として残す。
8. KnowledgeStore は findings を検索して次の action に使う。
9. promotion と learning を分ける。

## まとめ

optagent のエージェント像は、次の一文にまとめられます。

> 最適化を、予測を持った action による状態遷移として扱い、観測された証拠から
> 判断と知識を更新し続けるエージェント。

この考え方を、状態モデルと workflow の両方に反映する必要があります。
