# E03 — two independent groups, one escaping and one not

**Written before the run.**

The boundary program. Meet 3 asked what makes a cluster boundary a boundary; E03 answers by
building two groups that are **identical in shape** and differ only by a `putstatic`. Any
difference in the picture is attributable to that one line and nothing else.

## Program

```java
public class E03 {
    static Box published;
    public static void main(String[] args) {
        Box kept = new Box();          // BCI 0    group 1
        Item tucked = new Item();      // BCI 8
        kept.item = tucked;            // BCI 18

        Box leaked = new Box();        // BCI 21   group 2 - same shape
        Item exposed = new Item();     // BCI 29
        leaked.item = exposed;         // BCI 41
        published = leaked;            // BCI 45   <- the whole difference
    }
}
class Box  { Item item; }
class Item { }
```

## Abstract objects — fact (javap)

All four in `<E03: void main(java.lang.String[])>`.

| id | var | BCI | type | node |
|---|---|---:|---|---|
| O1 | `kept`    | 0  | `Box`  | `<internal,0>`  |
| O2 | `tucked`  | 8  | `Item` | `<internal,8>`  |
| O3 | `leaked`  | 21 | `Box`  | `<internal,21>` |
| O4 | `exposed` | 29 | `Item` | `<internal,29>` |

`putfield` at 18 and 41, `putstatic` at 45.

## Reading A — patched (`MarkStoreEscaping=false`)

### Edges

| # | edge | fieldPath | provenance |
|---|---|---|---|
| e1–e4 | each Oi → its constructor's `<parameter,-1>` | — | `ARGUMENT` |
| e5 | O2 → O1 | `.item` | `CONTAINMENT` (store at 18) |
| e6 | O4 → O3 | `.item` | `CONTAINMENT` (store at 41) |

Predicted `Fields:{<internal,0>={item=[<internal,8>]}, <internal,21>={item=[<internal,29>]}}`.

**The two groups share no edge.** They are disconnected components of the heap graph. That is
what makes the boundary structural rather than merely a difference of colour.

### Verdicts — prediction

| object | verdict | why |
|---|---|---|
| O1 `kept`    | `NoEscape` | never published |
| O2 `tucked`  | `NoEscape` | inherits O1 |
| O3 `leaked`  | `Escape`   | `putstatic` at 45 → `cascadeEscape` |
| O4 `exposed` | `Escape`   | cascade reaches it through the `item` edge from O3 |

All four correct for the program.

### Sets

- **S**: `S0 = {O1, O2}` `{NoEscape}`; `S1 = {O3, O4}` `{Escape}` ⟹ **2 sets, 2 colours.**
- **C**: four singletons — two chains, no cycles ⟹ **4 sets.**

**Here S is exactly right and C is exactly wrong.** S recovers the two groups a person would
draw. C shreds them into four, because co-escape is not mutual dependence and a chain is not a
cycle. E03 is the clearest single argument in the corpus for S over C.

## Reading B — upstream (`MarkStoreEscaping=true`)

Both stores short-circuit. `Fields:` empty, no containment edges.

| object | verdict |
|---|---|
| O1 `kept` | `NoEscape` — the only object never appearing as a store RHS |
| O2 `tucked` | `Escape` — **false positive**, nothing can observe it |
| O3 `leaked` | `Escape` — correct |
| O4 `exposed` | `Escape` — correct |

### Prediction summary

| quantity | patched | upstream |
|---|---:|---:|
| objects | 4 | 4 |
| `NoEscape` / `Escape` | 2 / 2 | 1 / 3 |
| containment edges | 2 | 0 |
| sets under S | 2 | 2 |
| sets under C | 4 | 4 |

**Both configurations report 2 sets under S, and the two partitions are different:**
`{kept,tucked} / {leaked,exposed}` versus `{kept} / {tucked,leaked,exposed}`. The set *count* is
identical and the *grouping* is not. A table of counts cannot tell these apart; the figure can.
This is the same effect first seen on M01 and it is worth stating once per program it occurs in.
