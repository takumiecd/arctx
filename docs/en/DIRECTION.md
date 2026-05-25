# Direction

The canonical graph model is now:

```text
Node -> Transition -> Node -> Transition -> Node
```

There are no specialized transition record types. Payloads attach meaning to a
plain `Transition`.

Future UI work should render the DAG visually and show payload details only for
the focused node or transition.
