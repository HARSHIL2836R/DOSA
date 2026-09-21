# E07 — a two-object cycle

**Written before the run.**

The program that exists to make the SCC question of `Clustering-Design` §4 option A appear on
one page. It is also the program where my earlier claim about S-vs-C needs correcting, and the
correction is written **before** the run so it cannot be mistaken for hindsight.

## Program

```java
public class E07 {
    public static void main(String[] args) {
        Node a = new Node();   // BCI 0
        Node b = new Node();   // BCI 8
        a.next = b;            // putfield at 18
        b.next = a;            // putfield at 23
    }
}
class Node { Node next; }
```

Nothing escapes. No static field, no return, no call out.

## Abstract objects — fact (javap)

| id | var | BCI | type | node |
|---|---|---:|---|---|
| O1 | `a` | 0 | `Node` | `<internal,0>` |
| O2 | `b` | 8 | `Node` | `<internal,8>` |

## Reading A — patched (`MarkStoreEscaping=false`)

### Edges — prediction

| # | edge | fieldPath | provenance |
|---|---|---|---|
| e1 | O1 → `⟨Node.<init>,<parameter,-1>⟩` | — | `ARGUMENT` |
| e2 | O2 → `⟨Node.<init>,<parameter,-1>⟩` | — | `ARGUMENT` |
| e3 | O1 → O2 | `.next` | `CONTAINMENT` (store at 18) |
| e4 | O2 → O1 | `.next` | `CONTAINMENT` (store at 23) |

Predicted `Fields:{<internal,0>={next=[<internal,8>]}, <internal,8>={next=[<internal,0>]}}` —
the cycle, in the PTG.

### A prediction that the mechanism forces, carried over from M01 (F3.4)

The summary will **not** show `[F]` false-clones between O1 and O2, even though both stores run.
`ConditionalValue.hashCode()` omits `isReal` while `equals()` compares hashcodes, so
`⟨Node.<init>,p-1,F⟩` equals `⟨Node.<init>,p-1,T⟩` and the `HashSet` absorbs it. Both objects
call the *same* constructor, so both clones vanish.

Predicted summary for each: `[<<Node: void <init>()>,<parameter,-1>,[T]>]` and nothing else.

**This is why the cycle is only visible in `Fields:`.** If the extractor read containment from
`[F]` markers, E07 would render as two unconnected nodes and the SCC would not exist. E07 is the
regression test for that decision.

### Verdicts — prediction

Both `NoEscape`. Neither object is reachable from outside `main`, and a cycle between two local
objects does not change that.

### Sets — and the correction

- **S**: both `{NoEscape}` ⟹ **1 set.**
- **C**: `{O1, O2}` is a strongly connected component ⟹ **1 set.**

**S and C agree on E07.** Earlier in this project I said E07 would make them disagree "in the
opposite direction" from E01. That was wrong, and the reasoning is simple: C can only ever
*merge* along cycles, and here the cycle joins two objects that S had already put together
because they share a verdict. Agreement is the correct outcome and it is still informative — it
shows that **C's merges are a subset of the structure S groups by**, at least when nothing
escapes.

The genuinely interesting E07 result is in the other configuration.

## Reading B — upstream (`MarkStoreEscaping=true`)

Both stores short-circuit to `cascadeEscape`. `a` is the RHS at 23 and `b` is the RHS at 18, so
**both** are marked `Escape` — unlike E01/E03, there is no surviving `NoEscape` object at all,
because in a cycle every object is somebody's store RHS.

`Fields:` empty, so **the cycle does not exist in the graph**.

| object | verdict | correct? |
|---|---|---|
| O1 `a` | `Escape` | **no** |
| O2 `b` | `Escape` | **no** |

- **S**: both `{Escape}` ⟹ **1 set.**
- **C**: no containment edges to condense ⟹ **2 singletons.**

**So the S-vs-C disagreement on E07 appears in the upstream configuration, not the patched one**
(1 vs 2), and it appears for a bad reason: C is finer only because the analysis threw the cycle
away. That is the opposite of what the disagreement is supposed to indicate, and it is a good
illustration of why an unaudited "number of clusters" metric would be actively misleading.

## Prediction summary

| quantity | patched | upstream |
|---|---:|---:|
| objects | 2 | 2 |
| `NoEscape` / `Escape` | 2 / 0 | 0 / 2 |
| containment edges | 2 | 0 |
| `[F]` clones in the summary | 0 (absorbed) | 0 |
| sets under S | 1 | 1 |
| sets under C | 1 | 2 |
| do S and C agree? | **yes** | **no** |
