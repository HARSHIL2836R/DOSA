# O08: Scoped Static Cache Lifetime

**Written before the run.** Semantics and formal specification as in
`02-Current-Work/02-Specs/2026-10-Formal-Semantics-Specification.md`: OWN(m) means the site's
objects are always in the subtree of the allocating method's oldest activation, UP(m) the same
for a proper caller m, HEAP neither.

## Bytecode facts (javap -c, Temurin 8u502-b07, -source 8 -target 8)

| id | site | what |
|---|---|---|
| A | `compute` bci 0, `Cache` | stored into static field `O08.cache` at bci 4 |
| B | `compute` bci 12, `Item` | stored into `cache.data` at bci 20 |

`compute` loads `O08.cache` at bci 24, reads `Cache.data` at bci 27, and cleans up with `cache = null` at bci 46. `main` calls `compute` twice and touches no static fields.

## Static Access Scope & LCA
- $\text{Accessors}(\text{O08.cache}) = \{ \text{compute} \}$
- Call graph: $\text{main} \to \text{compute}$
- Lowest Common Ancestor / Dominator in Call Graph SCC DAG:
  $$C_{\text{lca}}(\text{O08.cache}) = \text{sccOf}[\text{compute}]$$
- Since `compute` is not an entry point, $M_{\text{cap}}(\text{cache}) = \text{compute}$.

## Concrete ownership
While `compute` runs, `cache` holds A and A.data holds B. When `compute` returns, `cache` is null and its frame is gone, so both A and B are unreachable. Both objects live and die strictly inside `compute`'s activation.

## Predicted result

| site | Legacy (no Scope LCA) | Scope LCA ($G_B$) | why under Scope LCA |
|---|---|---|---|
| A | HEAP | OWN(compute), up=0 | `compute` dominates all accessors; edge `compute` $\to$ A; allocating method is `compute` |
| B | HEAP | OWN(compute), up=0 | allocated in `compute`, reached via A.data; dominated by `compute` |

Under Legacy, `GLOBAL` $\to$ A forces both sites into `HEAP`. Under Scope LCA, the static edge is attached to `compute` $\to$ A, restoring frame dominance.
