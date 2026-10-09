# O03: a container used by a frame and by a static

**Written before the run.** The ownership form of M02's allocation-site merging.

## Bytecode facts

| id | site | what |
|---|---|---|
| G | `O03.<clinit>` bci 0, `MyList` | stored by `putstatic global` at 7 |
| L | `local` bci 0, `MyList` | passed to `fill` at 9 |
| I | `fill` bci 1, `Item` | passed to `MyList.add` at 8 |
| N | `MyList.add` bci 0, `Node` | stored into `head` at 23 |

`main` calls `local` at 0 and `fill(global)` at 6.

## Concrete ownership

Two Items and two Nodes exist at run time. The pair created through `local` is reachable only
from L, and L only from `local`'s frame, so that pair dies when `local` returns. The pair created
through `fill(global)` is reachable from the static for the rest of the run.

## Predicted result

| site | B (v0) | N | truth |
|---|---|---|---|
| G | HEAP | HEAP | HEAP |
| L | OWN(local) | OWN(local) | OWN(local) |
| I | HEAP | HEAP | split: one object UP(local), one HEAP |
| N | HEAP | HEAP | split: one object UP(local), one HEAP |

Every Item and Node shares one abstract object, and that object is reachable from the static
through G, so the site is HEAP. No per-site rule can do better: the site's two objects have
different owners. Only context (object sensitivity on `MyList`) or a per-object test at run time
separates them. The dynamic study should count how often a site is split like this.
