# E04 — call to an unavailable callee

**Written before the run.** This is the one program in the corpus whose prediction has **two
branches**, and the run decides between them. Both branches are written out in advance so
neither can be claimed retrospectively.

The case the colouring has to handle **without pretending it resolved.**

## Program

```java
public class E04 {
    static native void sink(Box b);   // no body -> no summary -> unavailable callee

    public static void main(String[] args) {
        Box b = new Box();            // BCI 0
        sink(b);                      // BCI 9
    }
}
class Box { Item item; }
class Item { }
```

`native` is the cheapest way to get a callee that is genuinely unavailable: Soot loads the
method, so the call graph has an edge, but there is no body and therefore no entry in
`existingSummaries` at resolution time. No store, no static field, no return.

`Item` is declared (so `Box.item` has a type) but **never allocated** — so the program has
exactly one abstract object.

## Abstract objects — fact (javap)

| id | var | method | BCI | type | node |
|---|---|---|---:|---|---|
| O1 | `b` | `<E04: void main(java.lang.String[])>` | 0 | `Box` | `<internal,0>` |

`invokestatic E04.sink` at BCI 9.

## Edges — prediction

| # | edge | provenance | rule |
|---|---|---|---|
| e1 | O1 → `⟨Box.<init>,<parameter,-1>⟩` | `ARGUMENT` | receiver of `invokespecial` at 4 |
| e2 | O1 → `⟨E04.sink,<parameter,0>⟩` | `ARGUMENT` | §1.2 third bullet, the unavailable-callee rule. `JInvokeStmtHandler.handleExpr` loops over the callee's parameters and `cascadeCV(args.get(i), ⟨sink,<parameter,0>,[T]⟩)`. |

`sink` is native. `JInvokeStmtHandler` checks `blacklistedNatives`, which holds only three
`sun.misc.Unsafe` methods, so `E04.sink` is **not** blacklisted and takes the `cascadeCV` branch
rather than `cascadeEscape`. That is what makes e2 a conditional value instead of an escape.

**Pre-resolution prediction**, high confidence:

```
<internal,0> = [<<Box: void <init>()>,<parameter,-1>,[T]>, <<E04: void sink(Box)>,<parameter,0>,[T]>]
```

## Post-resolution — the two branches

`ReworkedResolver` has to resolve `⟨sink,<parameter,0>⟩` with no summary for `sink`.

**Branch 1 — the CV survives.** `<internal,0>` still carries
`⟨E04.sink,<parameter,0>,[T]⟩` after resolution. The object's status is neither `Escape` nor
`NoEscape`; it is *conditional on a parameter of a method we cannot see*. This is the honest
answer and the one PYE's framework is built to express.

**Branch 2 — it is forced to `Escape`.** The resolver treats "callee not in `existingSummaries`"
as ⊤ and purges the CV, giving `<internal,0> = [Escape]`. Sound, and consistent with
`Clustering-Design` §1.3's `notInSummaryCount` bucket, which counts exactly this situation and
returns `Integer.MAX_VALUE` (heap-only).

**Which I expect: Branch 2**, roughly 70/30. The `notInSummaryCount` counter in
`object_capturing_level` exists precisely because unavailable callees are given up on, and
`EscapeStatus.purge()` discards everything once `Escape` is present. But `.info` is written from
`ReworkedResolver.solvedSummaries`, not from the capture-level walk, so Branch 1 is possible.

**This is a prediction, not a hedge:** if Branch 1 holds the figure must show a node whose
outgoing edge terminates at a *callee parameter*, not at a sink, and it must **not** be coloured
as though it had a verdict. If Branch 2 holds, the figure shows an ordinary `Escape` and the
interesting content of E04 is the loss of information, which is then the finding.

## Sets

Either branch gives **one object**, hence:

- **S**: 1 set (trivially).
- **C**: 1 singleton — no containment edges anywhere in the program.

E04 is not about set counts. It is about whether an unresolved status is representable at all.

## Reading B — upstream (`MarkStoreEscaping=true`)

**Predicted identical to Reading A.** `MarkStoreEscaping` only affects `StoreStmt`, and E04
contains no field store of any kind. If the two configurations differ on E04, my model of the
flag is wrong and that is a finding about the flag, not about E04.

## Prediction summary

| quantity | patched | upstream |
|---|---:|---:|
| objects | 1 | 1 |
| containment edges | 0 | 0 |
| argument edges (in `main`) | 2 | 2 |
| sets under S | 1 | 1 |
| sets under C | 1 | 1 |
| `<internal,0>` post-resolution | `Escape` (branch 2, expected) or a surviving CV (branch 1) | same |

## What would refute the design

If `<internal,0>` shows **no** `⟨E04.sink,<parameter,0>⟩` CV even *pre*-resolution, then either
Soot dropped the call-graph edge to a native method, or the native branch in
`JInvokeStmtHandler` behaves differently from my reading of it. Check the pre-resolution half
first; the post-resolution half cannot distinguish these.
