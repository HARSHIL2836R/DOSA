# E05 — escape by return

**Written before the run.**

The first program in the corpus where one object exists under **two names in two methods**, so
it is also the smallest test of the Phase 7 interprocedural stitcher.

## Program

```java
public class E05 {
    static Box make() {
        Box b = new Box();     // BCI 0 in make
        return b;              // areturn at BCI 9
    }
    public static void main(String[] args) {
        Box r = make();        // invokestatic at 0, astore_1 at 3
    }
}
class Box { Item item; }
class Item { }
```

Nothing is stored, nothing reaches a static field. The **only** escape route is the `return`.

## Abstract objects — fact (javap)

| id | method | BCI | node | what |
|---|---|---:|---|---|
| O1 | `<E05: Box make()>` | 0 | `<internal,0>` | the allocation |
| X1 | `<E05: void main(java.lang.String[])>` | 3 | `<external,3>` | the call result |

**X1's BCI is 3, not 0.** Established on M02 (F7.1): `getBCI` reads the `BytecodeOffsetTag` of
the whole Jimple assignment unit, which Soot tags at the `astore`, not at the `invokestatic`.
Recorded here as a fact carried forward, not a fresh prediction.

## Edges — prediction

| # | edge | provenance | rule |
|---|---|---|---|
| e1 | O1 → `⟨Box.<init>,<parameter,-1>⟩` | `ARGUMENT` | receiver at 4 |
| e2 | O1 → `⟨E05.make,<returnValue,0>⟩` | `RETURN` | `JReturnStmtHandler` / `ConditionalValue.getRetCV`. Prints with `[F]`. |
| e3 | X1 → `⟨E05.make,<returnValue,0>⟩` | `RETURN` | the caller's external object names the same return value |

e2 and e3 pointing at the **same** `<returnValue,0>` node is what lets the stitcher alias O1 and
X1 into one object (Phase 7 rule 1). Confirmed on M02 for `makeBox`; E05 is the minimal case.

No containment edges anywhere — there is not a single field store in the program.

## Verdicts — prediction, and a predicted conflict

| object | verdict | confidence | why |
|---|---|---|---|
| O1 `<internal,0>` in `make` | `Escape` | high | it leaves the allocating frame by being returned; that is what "escape by return" means, and M02's `makeBox` `<internal,0>` came back `Escape` |
| X1 `<external,3>` in `main` | **`NoEscape`** | medium | in `main`'s own frame nothing is done with `r` — it is never stored, never passed, never returned |

**If both hold, the alias class {O1, X1} contains one `Escape` and one `NoEscape`.** The Phase 7
stitcher joins with `Escape` winning (`EscapeStatus` is a disjunction) and sets
`"statusConflict": true` on the merged node. E05 is predicted to be the **first program to
trigger that flag**, which is why the flag was built rather than assumed unnecessary.

Worth being clear that this is not a contradiction in Stava. The two verdicts answer different
questions: *"does it escape `make`'s frame?"* (yes) and *"does it escape `main`'s frame?"* (no).
Per-method summaries are allowed to disagree; a merged interprocedural node has to pick, and
picking `Escape` is the sound choice.

## Sets

**Per-method view** (`graph.json`): two objects.
- **S**: `{O1}` `Escape`, `{X1}` `NoEscape` ⟹ **2 sets.**
- **C**: two singletons, no containment ⟹ **2 sets.**

**Interprocedural view** (`graph-interproc.json`): one merged object.
- **S**: **1 set.** **C**: **1 set.**

## Reading B — upstream (`MarkStoreEscaping=true`)

**Predicted identical to Reading A**: E05 has no field store, so `MarkStoreEscaping` never fires.
Same objects, same edges, same verdicts. Together with E04 this gives two programs where the two
configurations *must* agree — a useful control, because if they differ, the difference is coming
from somewhere other than the store rule.

## Prediction summary

| quantity | patched | upstream |
|---|---:|---:|
| objects (per-method) | 2 | 2 |
| containment edges | 0 | 0 |
| return edges | 2 | 2 |
| merged objects (interproc) | 1 | 1 |
| `statusConflict` on the merged node | **yes** | yes |
| sets under S (per-method / interproc) | 2 / 1 | 2 / 1 |
| sets under C (per-method / interproc) | 2 / 1 | 2 / 1 |
