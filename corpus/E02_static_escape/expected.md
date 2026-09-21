# E02 — `a.f = b` where `a` reaches a static field

**Written before the run.** Predictions labelled; BCIs are `javap -c` facts.

E01 with one line added. Same two objects, same store, opposite verdict — so the pair
(E01, E02) isolates *what the static store does* and nothing else.

## Program

```java
public class E02 {
    static Box published;
    public static void main(String[] args) {
        Box b = new Box();      // BCI 0
        Item i = new Item();    // BCI 8
        b.item = i;             // BCI 18
        published = b;          // BCI 22   <- the only difference from E01
    }
}
class Box  { Item item; }
class Item { }
```

## Abstract objects — fact (javap)

| id | var | method | BCI | type | node |
|---|---|---|---:|---|---|
| O1 | `b` | `<E02: void main(java.lang.String[])>` | 0 | `Box`  | `<internal,0>` |
| O2 | `i` | same | 8 | `Item` | `<internal,8>` |

`putfield Box.item` at 18, `putstatic E02.published` at 22.

## Reading A — patched (`MarkStoreEscaping=false`)

### Edges

| # | edge | fieldPath | provenance | rule |
|---|---|---|---|---|
| e1 | O1 → `⟨Box.<init>,<parameter,-1>⟩`  | — | `ARGUMENT` | receiver of `invokespecial` at 4 |
| e2 | O2 → `⟨Item.<init>,<parameter,-1>⟩` | — | `ARGUMENT` | receiver at 12 |
| e3 | O2 → O1 | `.item` | `CONTAINMENT` | store at 18. §1.2 Store rule, PTG `Fields:{<internal,0>={item=[<internal,8>]}}` |

`putstatic` at 22 is **not** an edge. `StoreStmt.StaticStoreStmt` calls
`ptg.cascadeEscape(b)`, which sets O1 `Escape` outright and recurses through `Fields:` to O2.
It is a sink assignment, not a dependence.

### Verdicts — prediction

| object | verdict | why |
|---|---|---|
| O1 | `Escape` | `cascadeEscape` from the `putstatic` |
| O2 | `Escape` | `recursiveCascadeEscape` reaches it through the `item` field edge, which exists because the store at 18 precedes the `putstatic` at 22 |

Both correct: a static field is reachable from anywhere, and `i` is reachable from it.

### Sets

- **S**: both `{Escape}` ⟹ **1 set. One colour.**
- **C**: `O2 —.item→ O1` is a chain, no cycle ⟹ **2 sets.**

## Reading B — upstream (`MarkStoreEscaping=true`)

The store at 18 short-circuits to `cascadeEscape(i)` and **e3 is never created**; `Fields:` stays
empty. The `putstatic` at 22 hits the same short-circuit (`rhs` is a `Local`) and escapes O1.

| quantity | patched | upstream |
|---|---:|---:|
| objects | 2 | 2 |
| `NoEscape` / `Escape` | 0 / 2 | 0 / 2 |
| containment edges | 1 | 0 |
| sets under S | 1 | 1 |
| sets under C | 2 | 2 |

**E02 is the one program where both configurations give the same counts** — because everything
escapes either way, so over-approximating cannot make it worse. The configurations still differ
in the *graph*: patched has the `item` edge, upstream has nothing. If the figures look identical,
that is the bug; the containment edge must be visible in one and absent in the other.

## Contrast with E01, which is the point of this program

| | E01 | E02 |
|---|---|---|
| objects, edges | identical | identical |
| verdicts (patched) | both `NoEscape` | both `Escape` |
| sets under S | 1 | 1 |

**Same shape, same single S-set, opposite verdict.** This is what "colour means equi-escape set,
not escape verdict" has to survive: E01 and E02 both render as one colour, and the colour does
not tell you which. The verdict is on the sink edge and in the node text, where it belongs.
