# O01: one tree per frame

**Written before the run.** Semantics and labels as in
`02-Current-Work/01-Design/2026-09-24-Ownership-Trees.md`: OWN(m) means the site's objects are
always in the subtree of the allocating method's oldest activation, UP(m) the same for a proper
caller m, HEAP neither. Graph B is the borrow graph (v0); graph N gives every local an edge.

## Bytecode facts (javap -c, Temurin 8u502-b07, -source 8 -target 8)

| id | site | what |
|---|---|---|
| A | `main` bci 0, `Box` | main's own Box |
| B | `main` bci 9, `Item` | stored into A at bci 16 |
| C | `build` bci 0, `Box` | returned at bci 20 |
| D | `build` bci 9, `Item` | stored into C at bci 16 |

`use` has a `getfield Box.item` at 1 and a `putfield Item.n` at 7, and allocates nothing.

## Concrete ownership

After `build` returns, C and D are reachable only through main's local `c`. While `use` runs, its
frame also holds C and D, but `use` is younger than `main`, so main's frame still dominates both.
All four objects are in main's subtree for their whole lives.

## Predicted result

| site | B (v0) | N | why |
|---|---|---|---|
| A | OWN(main) | OWN(main) | only main's `new` reaches it |
| B | OWN(main) | OWN(main) | main's `new` and A.item; A is main's |
| C | UP(main), 1 up | UP(main) | build's `new`, and main receives it as a call result; main dominates build |
| D | UP(main), 1 up | UP(main) | build's `new` and C.item |

Graph B gives `use` no edge at all: `x` is a parameter and `i` a field read. Graph N gives `use`
edges to C and D, which change nothing because main dominates `use`.
