# O09: Cross-Frame Static Lifetime Under Controller

**Written before the run.** Semantics and formal specification as in
`02-Current-Work/02-Specs/2026-10-Formal-Semantics-Specification.md`: OWN(m) means the site's
objects are always in the subtree of the allocating method's oldest activation, UP(m) the same
for a proper caller m, HEAP neither.

## Bytecode facts (javap -c, Temurin 8u502-b07, -source 8 -target 8)

| id | site | what |
|---|---|---|
| A | `setup` bci 0, `Session` | stored into static field `O09.session` at bci 4 |
| B | `setup` bci 12, `Item` | stored into `session.item` at bci 20 |

`work` loads `O09.session` at bci 0, null-checks, and reads `Session.item` at bci 9.
`runSession` invokes `setup` at bci 0 and `work` at bci 4.
`main` invokes `runSession` twice and touches no static fields.

## Static Access Scope & LCA
- $\text{Accessors}(\text{O09.session}) = \{ \text{setup}, \text{work} \}$
- Call graph: $\text{main} \to \text{runSession} \to \text{setup}$, $\text{runSession} \to \text{work}$
- Lowest Common Ancestor / Dominator in Call Graph SCC DAG:
  $$C_{\text{lca}}(\text{O09.session}) = \text{sccOf}[\text{runSession}]$$
- Since `runSession` is not an entry point, $M_{\text{cap}}(\text{session}) = \text{runSession}$.

## Concrete ownership
While `runSession` executes, `session` holds A across the boundary between `setup` and `work`.
Both `setup` and `work` are called solely under `runSession`. Once `runSession` completes (or if overwritten in the next iteration), the session instance is confined to that invocation. Its lifetime is bounded by the controller frame `runSession`.

## Predicted result

| site | Legacy (no Scope LCA) | Scope LCA ($G_B$) | why under Scope LCA |
|---|---|---|---|
| A | HEAP | UP(runSession), up=1 | `runSession` dominates all accessors; edge `runSession` $\to$ A; allocating method is `setup`; distance from `runSession` to `setup` is 1 |
| B | HEAP | UP(runSession), up=1 | allocated in `setup`, reached via A.item; dominated by `runSession`; distance is 1 |

Under Legacy, `GLOBAL` $\to$ A forces both sites into `HEAP`. Under Scope LCA, the static edge is attached to `runSession` $\to$ A, capturing both sites at caller frame level 1!
