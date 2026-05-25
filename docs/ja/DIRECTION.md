# Direction

canonical graph model:

```text
Node -> Transition -> Node -> Transition -> Node
```

特殊な transition record type は持ちません。payload が plain `Transition`
に意味を付けます。

今後の UI は DAG を図として表示し、focus 中の node / transition の payload
だけを詳細表示する方針です。
