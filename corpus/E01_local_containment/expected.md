# E01 — local containment, both NoEscape

**Written before any Stava run.** Every value below is derived by hand from the Jimple/PYE
rules in `Clustering-Design` §1.2 and from `javap` output. Nothing here was read off a Stava
result. Where I predict a number it is labelled **prediction**; where I state a bytecode fact
it is labelled **fact (javap)**.

## Program

```java
public class E01 {
    public static void main(String[] args) {
        Box b = new Box();      // BCI 0
        Item i = new Item();    // BCI 8
        b.item = i;             // BCI 18, putfield Box.item
    }
}

class Box  { Item item; }
class Item { }
```

10 lines. Two allocation sites, one field store, no static field, no reference returned, no
call to anything outside the program except `Object.<init>`.

## Bytecode facts (javap -c, Temurin 8u502-b07, `-source 8 -target 8`)

`E01.main([Ljava/lang/String;)V`:

| BCI | instruction | meaning |
|---:|---|---|
| 0  | `new Box`                     | allocation site of O1 |
| 4  | `invokespecial Box."<init>"`  | receiver = O1 |
| 8  | `new Item`                    | allocation site of O2 |
| 12 | `invokespecial Item."<init>"` | receiver = O2 |
| 18 | `putfield Box.item:LItem;`    | the store `b.item = i` |
| 21 | `return`                      | |

`Box.<init>()V` and `Item.<init>()V` are each `aload_0; invokespecial Object."<init>"; return`.

Stava keys an abstract object on the `BytecodeOffsetTag` of the Jimple unit `$r = new T`
(`ptg/ObjectFactory.getObj` → `utils.getBCI.get`), so the object refs are the offsets of the
`new` instructions: **0 and 8**. Fact about how the key is computed, read from source, not a
prediction.

## Abstract objects

| id | allocation site (method, BCI) | Java type | Stava `ObjectNode` | kind |
|---|---|---|---|---|
| O1 | (`<E01: void main(java.lang.String[])>`, 0) | `Box`  | `<internal,0>` | object |
| O2 | (`<E01: void main(java.lang.String[])>`, 8) | `Item` | `<internal,8>` | object |

Two further nodes exist but are **not allocations** — the `this` parameters of the two
constructors, which are what the argument edges point at:

| id | node | kind |
|---|---|---|
| P_Box  | (`<Box: void <init>()>`, `<parameter,-1>`)  | param |
| P_Item | (`<Item: void <init>()>`, `<parameter,-1>`) | param |

`E01.<init>()` also exists and holds its own `<parameter,-1>`, but no `E01` instance is ever
allocated (`main` is static), so it contributes an isolated node with no edge into the `main`
graph.

---

## Reading A — the rules as `Clustering-Design` §1.2 states them

The PYE semantics the design document describes. This is what I would draw on paper given
§1.2 alone.

### Edges

| # | edge | fieldPath | provenance | rule |
|---|---|---|---|---|
| e1 | O1 → P_Box  | — | `ARGUMENT` | receiver of `invokespecial Box.<init>` at BCI 4. `JInvokeStmtHandler.handleExpr`: for an `InstanceInvokeExpr`, `cascadeCV(base, ⟨callee, <parameter,-1>, isReal=T⟩)`. §1.2 third bullet (the callee rule). |
| e2 | O2 → P_Item | — | `ARGUMENT` | same, receiver of `invokespecial Item.<init>` at BCI 12. |
| e3 | O2 → O1     | `.item` | `CONTAINMENT` | the store `b.item = i` at BCI 18. §1.2 first bullet, `handlers/JAssignStmt/StoreStmt.java`, PYE §5.1 Store rule: *"`a.f = b` adds `g_m(O_a)` into `g_m(O_b)`"* — the contained object inherits the container's status, so **O2 escapes if O1 escapes**. |

No Load rule fires (nothing reads `b.item`). No unavailable-callee case (both constructors
are application classes with bodies).

### Shape the edge actually takes in `.info` — prediction

Stated explicitly because the Phase 4 extractor depends on it. `StoreStmt.storeStmt` does not
add a node "O1" to O2's status. It calls `PointsToGraph.propagateES`, which takes the
container's status, calls `makeFalseClone()` on it, and adds the result to the contained
object's status. `ConditionalValue.makeFalseClone()` rebuilds the CV with `isReal = false`.

So I predict O2's pre-resolution summary is **not** `[⟨Item.<init>,p-1,T⟩, O1]` but:

```
<internal,8> = [<<Item: void <init>()>,<parameter,-1>,[T]>, <<Box: void <init>()>,<parameter,-1>,[F]>]
```

i.e. **a containment edge shows up as a copy of the container's out-edges with `isReal`
flipped to `F`.** That gives Phase 4 its provenance rule: in the pre-resolution half of a
`.info` file, a CV printed `[T]` is `ARGUMENT`, a CV printed `[F]` is `CONTAINMENT`-derived.
**Prediction, to be confirmed or refuted by the Phase 2 run.** If refuted, the extractor's
provenance tagging is wrong and Phase 4 changes — not this file.

### Sinks — prediction

`Box.<init>` and `Item.<init>` each only call `Object.<init>()` on `this` and never store it
anywhere, so their `<parameter,-1>` resolves to `NoEscape`.

| object | resolves to |
|---|---|
| O1 | `NoEscape` |
| O2 | `NoEscape` (inherits O1's status through e3; O1 is `NoEscape`) |

Neither object is reachable from a static field, a return value, a thread, or a parameter of
an unanalysed method. Both are genuinely stack-allocatable. This is the correct answer for
this program.

### Equi-escape sets

**Definition S** (equal resolved `EscapeStatus` after `purge()`): both objects resolve to
exactly `{NoEscape}` ⟹ **one set, `S0 = {O1, O2}`. One colour.**

**Definition C** (same SCC of the dependency graph): the graph `O2 —.item→ O1 —arg→ P_Box`,
`O2 —arg→ P_Item` is a DAG, no cycles ⟹ **two sets, `C0 = {O1}`, `C1 = {O2}`. Two colours.**

**S and C already disagree on E01**, before we get anywhere near E07. That is expected and is
the point: S groups by *verdict*, C groups by *mutual dependence*, and a chain is not a cycle.
E07 is designed to make them disagree the other way — C merging two objects because of a
cycle, so the cycle does the work rather than the verdict.

---

## Reading B — the checkout as it is actually configured

`config/StoreEscape.MarkStoreEscaping` is `true` in `stava/`. `StoreStmt.handle` opens with:

```java
if (StoreEscape.MarkStoreEscaping) {
    if (rhs instanceof Local) { ptg.cascadeEscape((Local)rhs, summary); return; }
}
```

That `return` is taken before `storeStmt()` is ever reached. Consequence for E01: the store at
BCI 18 marks O2 `Escape` outright and **e3 is never created**; no PTG field edge is built
either, so `Fields:` stays empty.

### Edges — prediction

| # | edge | provenance | note |
|---|---|---|---|
| e1 | O1 → P_Box | `ARGUMENT` | survives |
| e2 | — | — | **destroyed.** `EscapeStatus.purgeAndEscape()` replaces O2's whole status set with `{Escape}`, discarding the `⟨Item.<init>,p-1,T⟩` CV. |
| e3 | — | — | **never created.** |

### Sinks — prediction

| object | resolves to |
|---|---|
| O1 | `NoEscape` |
| O2 | `Escape` |

O2's verdict is **wrong as a statement about the program** — nothing in E01 can observe the
`Item` from outside `main`. It is not wrong as a statement about Stava, which is deliberately
over-approximating every field store.

### Equi-escape sets

**S**: `{NoEscape}` vs `{Escape}` ⟹ two sets. **C**: two singletons (one edge, no cycle) ⟹
two sets. S and C agree, but only because the structure that could distinguish them has been
erased.

### Corroboration that Reading B is what the checkout does

Not a prediction — the checked-in output of `stava/out/test1/Main.info` for
`A.n=B; B.n=C; C.n=D; D.n=B` (four `new Node()` at BCI 0/8/16/24):

```
Fields:{}
{<internal,24>=[Escape], <internal,8>=[Escape], <internal,0>=[NoEscape], <internal,16>=[Escape]}
```

`A` is the only object never appearing as a store RHS, and the only `NoEscape`. Empty
`Fields:`. Exactly Reading B.

---

## What I expect the Phase 2 run to report

Application-only filtering, so JDK objects excluded.

| quantity | Reading A | Reading B |
|---|---:|---:|
| abstract objects in `E01.main` | 2 | 2 |
| `NoEscape` after resolution | 2 | 1 |
| `Escape` after resolution | 0 | 1 |
| containment edges | 1 | 0 |
| argument edges | 2 | 1 |
| equi-escape sets under S | 1 | 2 |
| equi-escape sets under C | 2 | 2 |

The object **count** is 2 either way, so the Phase 2 gate ("within one or two of the count in
`expected.md`") passes under both readings and does not discriminate. What discriminates is
the `Escape`/`NoEscape` split and the presence of `Fields:`.

## Open decision this file forces

E01, E02, E03, E06 and E07 are all built on `a.f = b`. Under Reading B all five collapse to
"one `NoEscape` allocation, everything else `Escape`, no containment edges", and E07 cannot
form the SCC it exists to demonstrate. Either:

- **B1.** Run as-is and report Reading B. Honest, cheap, and the finding is *"Stava's default
  configuration erases the dependency graph this project set out to visualise."* A real Meet 5
  result, but the eight figures are then mostly the same degenerate figure.
- **B2.** Ship `patches/0001-store-escape-off.patch` flipping `MarkStoreEscaping` to `false`
  (one boolean in `config/StoreEscape.java`, never applied to the checkout — applied to a copy
  of the source under `heapviz/build/`), and render both configurations per program. Doubles
  the figure count, makes the Store rule visible, costs one extra run per program.

Not decided here. See `Micro-Corpus-Log.md` Phase 1.
