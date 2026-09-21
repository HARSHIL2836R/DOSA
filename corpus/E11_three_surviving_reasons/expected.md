# E11 — three escape reasons that survive `purge()`

**Written before the run.** Predictions are labelled; BCIs are `javap -c` facts.

E09 was supposed to be the ground truth for reason multiplicity 3 and **it came back with 2**.
The cause is recorded as F11.6 in [[Micro-Corpus-Log]] and is worth stating here because it is
the reason this program exists: E09's third reason was `return`, and `PointsToGraph.setAsReturn`
delivers "this object is returned" as a **conditional value**, through
`cascadeCV → EscapeStatus.addEscapeState → purge()`. `purge()` discards every alternative once
`Escape` is present. E09's object was already `Escape` from the monitor and the static store by
the time the `areturn` was reached, so the return conditional value was destroyed on arrival, no
`<returnValue,0>` node was ever created for `make()`, and no site anywhere could record the
third reason.

E11 is E09 with the `return` replaced by a `throw`. `throw` is handled by
`JThrowStmtHandler:19`, which calls `setEscape()` **directly** on an object it already has in
hand — it does not go through the conditional-value lattice at all, so `purge()` cannot destroy
it. All three of E11's reasons are recorded at handler sites that are unconditional in this
sense.

**The general rule this pins down, and it is the reportable one:** a reason survives to be
counted iff it is recorded at a site that mutates the summary directly. A reason delivered as a
conditional value is destroyed by `purge()` whenever the object already escapes — which is
exactly when multiplicity would have been greater than one. The observable multiplicity ceiling
is therefore set by the lattice, not by the program.

## Program

```java
public class E11 {
    static Oops published;

    static void make() {
        Oops o = new Oops();     // BCI 0
        synchronized (o) { }     // monitorenter BCI 11
        published = o;           // putstatic    BCI 23
        throw o;                 // athrow       BCI 27
    }

    public static void main(String[] args) {
        try { make(); } catch (Oops e) { }
    }
}
class Oops extends RuntimeException { }
```

`make()` is byte-for-byte E09's `make()` up to BCI 26; only the final instruction differs
(`athrow` at 27 instead of `areturn` at 27), and the return type is `void` instead of `Item`.
That is deliberate: the pair (E09, E11) isolates *what the delivery mechanism of the third
reason does* and nothing else, the same way (E01, E02) isolates what the static store does.

## Abstract objects — fact (`javap -c`)

| id | var | method | BCI | node | designated? |
|---|---|---|---:|---|---|
| O1 | `o` | `<E11: void make()>` | 0 | `<internal,0>` | yes |
| O2 | — | `<E11: void make()>` | -1 | `<external,-1>` | no — `javac`'s catch-all for the `synchronized` block, exception table `12–14 → 17`, `17–20 → 17`, rethrown by `athrow` at 21 |
| O3 | — | `<E11: void main(java.lang.String[])>` | -1 | `<external,-1>` | no — the `catch (Oops e)` handler, exception table `0–3 → 6` |

## Reading A — patched (`MarkStoreEscaping=false`)

### The three sites that fire on O1, and why each survives

| # | site | source line | constant | delivery |
|---|---|---|---|---|
| r1 | `monitorenter` at 11 | `MonitorStmtHandler.java:20` | `MONITOR` | `summary.get(obj).setEscape()` — direct |
| r2 | `putstatic` at 23 | `StoreStmt.java:117` `StaticStoreStmt` → `cascadeEscape` | `STATIC_FIELD_STORE` | `recursiveCascadeEscape` → `setEscape()` — direct |
| r3 | `athrow` at 27 | `JThrowStmtHandler.java:19` | `THROWN` | `summary.get(obj).setEscape()` — direct |

None of the three goes through `addEscapeState`, so none is subject to `purge()`. They are
recorded in the side map in the order they fire and the side map never removes anything.

### Prediction, per object

| object | reasons | count | real | surrender | verdict |
|---|---|---:|---:|---:|---|
| **O1** | `STATIC_FIELD_STORE`, `MONITOR`, `THROWN` | **3** | 3 | 0 | `Escape` |
| O2 | `CAUGHT_EXCEPTION`, `THROWN` | 2 | 2 | 0 | `Escape` |
| O3 | `CAUGHT_EXCEPTION` | 1 | 1 | 0 | `Escape` |

`.reasons` prints an `EnumSet`, which iterates in **declaration order**, not firing order. The
declaration order in `es/EscapeReason.java` puts `STATIC_FIELD_STORE` before `MONITOR` before
`THROWN`, so the line is predicted to read exactly:

```
<E11: void make()>	0	internal	STATIC_FIELD_STORE,MONITOR,THROWN
```

### Reason multiplicity, the thing being measured

Three objects, three distinct reason sets, of sizes 3, 2 and 1 — so E11 alone populates the
`reasonCount` histogram at 1, 2 and 3 and is the smallest program in the corpus for which
figure 2 has more than one non-empty bar.

## Reading B — upstream (`MarkStoreEscaping=true`)

`StoreStmt.java:38-41` short-circuits before the LHS is examined, so r2 becomes
`STORE_CASCADE_UNTYPED` and the static store is never identified as a static store.

| object | patched | upstream |
|---|---|---|
| O1 | `STATIC_FIELD_STORE`, `MONITOR`, `THROWN` | `STORE_CASCADE_UNTYPED`, `MONITOR`, `THROWN` |
| O2 | `CAUGHT_EXCEPTION`, `THROWN` | `CAUGHT_EXCEPTION`, `THROWN` |
| O3 | `CAUGHT_EXCEPTION` | `CAUGHT_EXCEPTION` |

**Cardinality is identical in both configurations; the naming is not.** That is the same result
E09 gives and it is the one that matters for the benchmark: the multiplicity axis is stable
across the flag, and the *identity* of the dominant reason is not.

## What this program cannot show

- Nothing about frequency: one hand-planted object, chosen to hit three sites.
- It does not rescue the return reason. `return` is still unobservable on an already-escaping
  object, in this program and in every other; E11 works around that, it does not fix it.
- Three is not a ceiling that was measured, only one that was reached. Nothing here says how
  many reasons a real program's objects carry.
- O2 and O3 are `javac` artefacts of `synchronized` and `catch`, not things a person wrote, and
  must not be quoted as hand-authored multi-reason objects.
