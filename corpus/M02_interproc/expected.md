# M02 — interprocedural PTG, and what allocation-site merging costs

**Written before the run.** Predictions labelled as such; bytecode facts from `javap -c`.

Purpose: a heap graph that only makes sense when the per-method PTGs are stitched together, so
the figure shows what a **fully interprocedural PTG** would look like rather than one method's
slice. Folds in E05 (escape by return), E06 (store into a field of a parameter), E07 (cycle)
and E08 (one allocation site, two owners).

## Bytecode facts (javap -c, Temurin 8u502-b07, -source 8 -target 8)

`main`: `invokestatic makeBox` at **0** and **17**; `new Item` at **4** and **21**;
`invokestatic fill` at 14 and 33; `invokestatic publish` at 37; `new Node` at **40** and **49**;
`putfield Node.next` at 62 and 69.

`makeBox`: `new Box` at **0** — one site. `fill`: `putfield Box.item` at 2.
`publish`: `putstatic M02.published` at 1.

## Abstract objects, per method

| id | method | node | Java type | note |
|---|---|---|---|---|
| B  | `makeBox` | `<internal,0>`   | `Box`  | **one abstract object for both `a` and `b`** |
| I1 | `main`    | `<internal,4>`   | `Item` | `i` |
| I2 | `main`    | `<internal,21>`  | `Item` | `j` |
| P  | `main`    | `<internal,40>`  | `Node` | `p` |
| Q  | `main`    | `<internal,49>`  | `Node` | `q` |
| X1 | `main`    | `<external,0>`   | —      | result of `makeBox()` at BCI 0 |
| X2 | `main`    | `<external,17>`  | —      | result of `makeBox()` at BCI 17 |

Plus parameter nodes: `fill`'s `<parameter,0>` / `<parameter,1>`, `publish`'s `<parameter,0>`,
`main`'s `<parameter,0>` (`args`).

## The stitching rules being tested

1. **ARGUMENT binding.** If an object `O` in the caller carries `⟨u,<parameter,i>,[T]⟩`, then
   `O` is passed as argument `i` to `u`, so `(u, parameter i)` binds to `O`.
   Predicted: `fill.param0 ← {X1, X2}`, `fill.param1 ← {I1, I2}`, `publish.param0 ← {X2}`.
2. **RETURN binding.** `X1` and `X2` are `external` objects created because the RHS is an
   `InvokeExpr`; the callee at that BCI is `makeBox`, whose returned object is `B`. So `X1` and
   `X2` both alias `B` and are **collapsed into it**.
3. **Parameter elimination.** A callee field edge `<parameter,0> --item--> <parameter,1>` is
   rewritten through the bindings into caller-level object edges.

## Predicted interprocedural PTG (patched build, `MarkStoreEscaping=false`)

After collapsing X1 and X2 into B and eliminating parameter nodes, `fill`'s single field edge
becomes **two** edges out of one node:

```
   Box@makeBox:0  --item-->  Item@main:4      (from fill(a, i))
   Box@makeBox:0  --item-->  Item@main:21     (from fill(b, j))
   Node@main:40   --next-->  Node@main:49
   Node@main:49   --next-->  Node@main:40
```

**That single `Box` node with two outgoing `item` edges is the whole allocation-site-merging
problem in one picture.** `a` and `b` are distinct at run time and each has its own `Item`; the
analysis cannot tell them apart because they were born at the same `new`.

## Predicted verdicts

`publish(b)` does `published = box`, so `publish.param0` escapes. It binds to `X2`, which has
been collapsed into `B` — and `B` is *also* what `a` points to.

| object | predicted | why |
|---|---|---|
| B  `Box@makeBox:0` | `Escape` | published via `publish` |
| I2 `Item@main:21`  | `Escape` | contained in a published `Box` — **genuinely** escapes |
| I1 `Item@main:4`   | `Escape` | contained in `B` too — **a false positive.** `i` is only reachable through `a`, which is never published. It escapes solely because it shares an allocation site with `b`'s box. |
| P, Q `Node@main:40/49` | `NoEscape` | local cycle, never published |

**I1 is the measurement task 8 asks for, shown rather than argued:** one abstract object with
more than one distinct incoming containment source, and a verdict that is wrong because of it.

## Predicted partitions

- **S**: `{B, I1, I2}` all `Escape`; `{P, Q}` both `NoEscape` ⟹ **2 sets.**
- **C** (SCC over containment): `{B}`, `{I1}`, `{I2}`, `{P, Q}` ⟹ **4 sets.**

## Predicted upstream build (`MarkStoreEscaping=true`)

`Fields:` empty in every method, so **no interprocedural PTG exists to draw at all** — the
stitching has nothing to stitch. Predicted verdicts: everything that is ever a store RHS is
`Escape`, i.e. I1, I2, B (via `publish`), P, Q. Possibly nothing survives as `NoEscape`.
**Prediction, lower confidence than the patched one**, because the interaction between
`cascadeEscape` and the parameter/return bindings across methods has not been traced by hand.

## What would refute the stitching

If `X1`/`X2` do **not** carry a resolvable link to `makeBox`'s returned object, rule 2 fails and
the two `Box` results appear as two unlinked external nodes — in which case the figure cannot be
called an interprocedural PTG and must be relabelled. Checked explicitly after the run.
