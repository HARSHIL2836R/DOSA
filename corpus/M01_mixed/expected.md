# M01 — three groups on one page

**Written before the run.** Method already validated on E01 (hand drawing agreed), so this is
shorter: it states the objects, the edges, the verdicts and the two set-partitions, and it does
so for both configurations.

Purpose: one figure for Meet 5 that carries E02 (escape via static field), E03 (two independent
groups, one escaping and one not) and E07 (two-object cycle) simultaneously, while staying
hand-checkable.

## Program (22 lines)

```java
public class M01 {
    static Box published;                  // the escape route: a static field

    public static void main(String[] args) {
        Box kept = new Box();              // group 1 — stays local
        Item tucked = new Item();
        kept.item = tucked;

        Box leaked = new Box();            // group 2 — same shape, but published
        Item exposed = new Item();
        leaked.item = exposed;
        published = leaked;

        Node p = new Node();               // group 3 — two-object cycle
        Node q = new Node();
        p.next = q;
        q.next = p;
    }
}
class Box  { Item item; }
class Item { }
class Node { Node next; }
```

Groups 1 and 2 are deliberately **identical in shape**. The only difference is the `putstatic`.
That is what makes the boundary between the two clusters legible rather than asserted — Meet 3's
"what makes a boundary a boundary".

## Abstract objects — fact (javap -c, Temurin 8u502-b07, `-source 8 -target 8`)

All six are allocated in `<M01: void main(java.lang.String[])>`.

| id | var | BCI | type | `ObjectNode` |
|---|---|---:|---|---|
| O1 | `kept`    | 0  | `Box`  | `<internal,0>`  |
| O2 | `tucked`  | 8  | `Item` | `<internal,8>`  |
| O3 | `leaked`  | 21 | `Box`  | `<internal,21>` |
| O4 | `exposed` | 29 | `Item` | `<internal,29>` |
| O5 | `p`       | 48 | `Node` | `<internal,48>` |
| O6 | `q`       | 57 | `Node` | `<internal,57>` |

Stores: `putfield Box.item` at 18 and 41, `putstatic M01.published` at 45, `putfield Node.next`
at 70 and 77. `published` has no initialiser, so there is no `<clinit>` and no seventh object.

---

## A design point this program forced, before any run

E01's derivation assumed the dependency graph is what `Clustering-Design` §1.2 calls `G_dep`:
edges `o → ⟨u,x⟩` read off the `Summary` block. Writing M01's cycle by hand exposed a problem
with using that graph alone for **Definition C**.

Stava does not realise a containment relation as an edge from the contained object to the
container. `StoreStmt.storeStmt` → `PointsToGraph.propagateES` **copies the container's
conditional values into the contained object** with `isReal` flipped to `F`
(`makeFalseClone`). So in the `Summary` block every edge terminates at a *(callee method,
parameter)* node. **No object → object edge is ever written there.**

Consequence: SCCs over `G_dep` alone are all singletons within a method, so Definition C would
be vacuous — including on this program's cycle, which is the case it was designed for. That is
not a bug in Stava; it is a consequence of `G_dep` being a dependence relation between
*program elements*, not a heap shape.

**Resolution, and it is the reason the PTG is dumped next to the summary.** The object → object
containment structure lives in the **`Fields:`** map of the PTG block:
`{<internal,0>={item=[<internal,8>]}, ...}`. The figure therefore draws:

| drawn as | source | provenance |
|---|---|---|
| object → object, labelled with the field | PTG `Fields:` | `CONTAINMENT` |
| object → (callee, parameter) | `Summary` CVs with `[T]` | `ARGUMENT` |
| *(not drawn)* | `Summary` CVs with `[F]` | `CONTAINMENT`, derived — the false-clones. Recorded in `graph.json` with `"derived": true` and suppressed in the figure, because they duplicate an edge the `Fields:` map already shows. Drawing them would double every containment edge. |

Definition C is computed over the `CONTAINMENT` edges. This is a **deviation from the literal
wording** of `Clustering-Design` §4 option A ("condense `G_dep`"), made because the literal
reading is vacuous, and it is flagged as such in the caption.

---

## Reading A — patched build (`MarkStoreEscaping=false`)

### Predicted containment edges (PTG `Fields:`)

| from | field | to |
|---|---|---|
| O1 `kept`   | `item` | O2 `tucked`  |
| O3 `leaked` | `item` | O4 `exposed` |
| O5 `p`      | `next` | O6 `q`       |
| O6 `q`      | `next` | O5 `p`       |

### Predicted argument edges (`Summary`, `[T]`)

Each of the six is the receiver of its own constructor, so six edges: O1, O3 → `⟨Box.<init>,
<parameter,-1>⟩`; O2, O4 → `⟨Item.<init>, <parameter,-1>⟩`; O5, O6 → `⟨Node.<init>,
<parameter,-1>⟩`. All three constructors are empty, so all three parameter nodes resolve
`NoEscape`.

### Predicted verdicts

| object | verdict | why |
|---|---|---|
| O1 `kept`    | `NoEscape` | never published; constructor does not leak `this` |
| O2 `tucked`  | `NoEscape` | inherits O1's status through the store at 18; O1 is `NoEscape` |
| O3 `leaked`  | `Escape`   | `putstatic` at 45 → `StoreStmt.StaticStoreStmt` → `cascadeEscape` |
| O4 `exposed` | `Escape`   | `cascadeEscape` recurses through `Fields:` from O3 (`recursiveCascadeEscape`), and the `leaked.item` edge already exists at BCI 45 because the store at 41 precedes it |
| O5 `p`       | `NoEscape` | cycle with O6; neither is published |
| O6 `q`       | `NoEscape` | as above |

### Predicted partitions

- **S** (equal resolved status): `S0 = {O1, O2, O5, O6}` all `{NoEscape}`; `S1 = {O3, O4}` both
  `{Escape}`. **2 sets.**
- **C** (SCC over `CONTAINMENT`): `{O1}`, `{O2}`, `{O3}`, `{O4}`, `{O5, O6}`. **5 sets.**

**S and C disagree: 2 vs 5.** The single place C merges anything is the cycle. Everywhere else C
is finer than S. This is the whole S-vs-C question on one page.

---

## Reading B — upstream build (`MarkStoreEscaping=true`, as shipped)

Every `a.f = b` short-circuits to `cascadeEscape(b); return`.

### Predicted edges

`Fields:` is **empty** — `STRONG_makeField` never runs. So **zero containment edges**, and the
figure has no heap structure in it at all. The only surviving argument edge is O1's; the other
five objects have had their CVs purged by `purgeAndEscape()`.

### Predicted verdicts

| object | verdict | why |
|---|---|---|
| O1 `kept`    | `NoEscape` | the only object that is never a store RHS |
| O2 `tucked`  | `Escape` | RHS of `kept.item = tucked` |
| O3 `leaked`  | `Escape` | RHS of `published = leaked` |
| O4 `exposed` | `Escape` | RHS of `leaked.item = exposed` |
| O5 `p`       | `Escape` | RHS of `q.next = p` |
| O6 `q`       | `Escape` | RHS of `p.next = q` |

Five of the six verdicts are **wrong as statements about the program**: `tucked`, `p` and `q`
cannot be observed from outside `main`. They are correct as statements about Stava, which
over-approximates every field store.

### Predicted partitions

- **S**: `{O1}` and `{O2, O3, O4, O5, O6}`. **2 sets** — the same *count* as Reading A, but
  completely different membership. A count alone would not have caught this; the picture does.
- **C**: six singletons (no containment edges to condense). **6 sets.**

---

## Prediction summary

| quantity | patched | upstream |
|---|---:|---:|
| abstract objects | 6 | 6 |
| `NoEscape` | 4 | 1 |
| `Escape` | 2 | 5 |
| containment edges | 4 | 0 |
| argument edges | 6 | 1 |
| sets under S | 2 | 2 |
| sets under C | 5 | 6 |

## Filter statement (for the caption)

Application classes only: `M01`, `Box`, `Item`, `Node`. Achieved by reading only those four
`.info` files out of the run's output directory — the `.info` files are already partitioned one
per declaring class, so this is exact rather than approximate. Everything else Soot loaded (the
JDK library classes that make [[Stava-Run-Guide]] §2 report 62–69 objects for a 5–40 line
program) is excluded. Edges whose *target* is a JDK method are kept and drawn as a library
boundary node, because dropping them would hide real dependencies.

**Not** the `-i`/`-x` Soot-argument filtering of `PTA-Task-List` task 10. That changes what Soot
analyses; this changes what is reported. For a figure the two are equivalent; for a cost or
population measurement they are not, and no such measurement is quoted from this run.
