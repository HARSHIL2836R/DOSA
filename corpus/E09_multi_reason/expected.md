# E09 — one object, three escape reasons at once

**Written before the run.** Predictions are labelled; BCIs are `javap -c` facts.

This is the ground truth for the **multiplicity axis**. Every other program in the corpus was
written to have one interesting escape; this one is written so that a single abstract object is
hit by three different reason-recording sites, so that "number of reasons" has a value other
than 0 or 1 that a person derived by hand.

## Program

```java
public class E09 {
    static Item published;

    static Item make() {
        Item i = new Item();        // BCI 0
        synchronized (i) { }        // monitorenter BCI 11
        published = i;              // putstatic    BCI 23
        return i;                   // areturn      BCI 27
    }

    public static void main(String[] args) {
        Item x = make();            // invokestatic BCI 0
    }
}
class Item { }
```

## Abstract objects — fact (`javap -c`)

| id | var | method | BCI | node | how it arises |
|---|---|---|---:|---|---|
| O1 | `i` | `<E09: Item make()>` | 0 | `<internal,0>` | `new Item` at 0 |
| O2 | — | `<E09: Item make()>` | 0 | `<returnValue,0>` | synthetic, `ConditionalValue.getRetCV` |
| O3 | — | `<E09: Item make()>` | -1 | `<external,-1>` | the **compiler-generated** catch-all of the `synchronized` block: `astore_2` at 17, `athrow` at 21 |
| P1 | `this`-less params | both methods | -1 / 0 | `<parameter,·>` | identity statements |

O3 is not hand-planted and is worth naming in advance so it is not mistaken for a bug.
`synchronized (i) { }` compiles to `monitorenter`/`monitorexit` **plus** an `any` exception
handler that rethrows (exception table `12–14 → 17`, `17–20 → 17`). Stava's
`JIdentityStmtHandler` gives every `@caughtexception` its own `<external,-1>` and marks it
`Escape` (`:49`); `JThrowStmtHandler` then marks the same object `Escape` again at the
`athrow`. So **O3 is predicted to carry two reasons, `CAUGHT_EXCEPTION` and `THROWN`**, for free.
It is a second, unplanned multi-reason object and it is a real one.

## Reading A — patched (`MarkStoreEscaping=false`), the configuration this program is for

### The three sites that fire on O1

| # | site | source line | constant |
|---|---|---|---|
| r1 | `monitorenter` at 11 | `MonitorStmtHandler.java:20` | `MONITOR` |
| r2 | `putstatic` at 23, `lhs instanceof StaticFieldRef && rhs instanceof Local` | `StoreStmt.java:117`, `StaticStoreStmt` → `cascadeEscape` | `STATIC_FIELD_STORE` |
| r3 | `areturn` at 27 | `JReturnStmtHandler:31` → `PointsToGraph.setAsReturn` → `cascadeCV` | see below |

r1 and r2 are **intraprocedural and unconditional**: both run inside
`StaticAnalyser.internalTransform`, both stamp `<internal,0>` directly, and neither depends on
resolution order. **Prediction: O1 carries `MONITOR` and `STATIC_FIELD_STORE` with certainty.**

r3 is the one that is not certain, and the reason it is not certain is worth stating, because it
is a fact about where Stava attributes a return rather than about the instrumentation.
`return i` does **not** stamp `<internal,0>`. It creates the synthetic `<returnValue,0>` node O2
and gives O1 a conditional value pointing at it, which `GenerateGraphFromSummary` turns into a
dependency edge `O1 → O2`. The resolver's `isReturnObject` test
(`ReworkedResolver.java:537`) then fires on **O2**, not on O1.

O1 therefore picks the return up only through the successor scan at `:688`, as
`TRANSITIVE_SUCCESSOR`, and only if O2's SCC component was resolved **before** O1's — the
components are resolved in the order `FindSCC` emits them and `isEscapingObject(nxt)` reads
`solvedSummaries`, which is empty for O2 until O2's component has run.

**Primary prediction:** O1 = `{MONITOR, STATIC_FIELD_STORE, TRANSITIVE_SUCCESSOR}`, **3 reasons**,
0 of them surrender.
**Alternative, if the component order does not cooperate:** O1 = `{MONITOR, STATIC_FIELD_STORE}`,
2 reasons, with `RETURNED` on O2 instead.

Either way the return is attributed somewhere in `make()`. If the alternative is what comes back,
that is a **finding about Stava's return attribution**, not a broken instrumentation, and the
gate on this program should be read as *O1 carries both intraprocedural reasons and the reason
count is ≥ 2 with the return visible on O1 or O2* — not as "exactly three or stop".

### Verdicts — prediction

| object | verdict | why |
|---|---|---|
| O1 | `Escape` | `cascadeEscape` from the `putstatic`; the monitor sets it too |
| O2 | `Escape` | `isReturnObject` → `SetComponent(Escape)` |
| O3 | `Escape` | `JIdentityStmtHandler:49` sets it at creation |

`NoEscape` count for `E09`: **0** application objects. This program is not about the verdict.

### Reason multiplicity, the thing being measured

| object | reasons | count | real | surrender |
|---|---|---:|---:|---:|
| O1 | `MONITOR`, `STATIC_FIELD_STORE`, `TRANSITIVE_SUCCESSOR` | 3 | 3 | 0 |
| O2 | `RETURNED` | 1 | 1 | 0 |
| O3 | `CAUGHT_EXCEPTION`, `THROWN` | 2 | 2 | 0 |

## Reading B — upstream (`MarkStoreEscaping=true`)

`StoreStmt.java:38-41` short-circuits **before** the LHS is examined. The `putstatic` at 23 has a
`Local` on the right, so it takes the short circuit and calls
`cascadeEscape(i, STORE_CASCADE_UNTYPED)`; `StaticStoreStmt` is never reached and the static
store is never identified as a static store.

**Prediction:** O1 = `{MONITOR, STORE_CASCADE_UNTYPED, TRANSITIVE_SUCCESSOR}` — the same
cardinality, with `STATIC_FIELD_STORE` replaced by `STORE_CASCADE_UNTYPED`.

| quantity | patched | upstream |
|---|---:|---:|
| reasons on O1 | 3 | 3 |
| of which name the actual language construct | 3 | **2** |
| `STATIC_FIELD_STORE` present | yes | **no** |

**That collapse is a result to report, not a bug to work around.** It is the concrete,
hand-derived instance of the general claim that under the shipped configuration the reason
distribution measures Stava's store policy rather than the program: the single most interesting
distinction on this axis — "allocation reaches a static field" — does not survive the default
flag, and the multiplicity is preserved only because two *other* reasons happen to fire.

## What this program cannot show

- It says nothing about how common three-reason objects are. It is one hand-planted object.
- It cannot distinguish "the reason set is right" from "the reason set is complete": a site that
  fires but was never instrumented is invisible here and everywhere else.
- O3's two reasons are a property of `javac`'s `synchronized` lowering, not of the source
  program, and must not be quoted as though a person wrote a two-reason object.
