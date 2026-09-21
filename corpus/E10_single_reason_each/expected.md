# E10 — three objects, one reason apiece

**Written before the run.** Predictions are labelled; BCIs are `javap -c` facts.

The companion to [E09](../E09_multi_reason/expected.md). E09 fixes the top of the multiplicity
axis by hand; this one fixes the bottom. Each designated object is put in its own method so that
nothing can leak a second reason onto it, and the three reasons chosen are the three that are
recorded by **intraprocedural handlers**, so none of them depends on resolution order.

## Program

```java
public class E10 {
    static Item published;

    static void statik()  { Item a = new Item(); published = a; }   // putstatic     BCI 9
    static void monitor() { Item b = new Item(); synchronized (b) { } }  // monitorenter BCI 11
    static void thrown()  { Oops c = new Oops(); throw c; }         // athrow        BCI 9

    public static void main(String[] args) {
        statik();
        monitor();
        try { thrown(); } catch (Oops e) { }
    }
}
class Item { }
class Oops extends RuntimeException { }
```

## Abstract objects — fact (`javap -c`)

| id | var | method | BCI | node | designated? |
|---|---|---|---:|---|---|
| O1 | `a` | `<E10: void statik()>`  | 0 | `<internal,0>` | yes |
| O2 | `b` | `<E10: void monitor()>` | 0 | `<internal,0>` | yes |
| O3 | `c` | `<E10: void thrown()>`  | 0 | `<internal,0>` | yes |
| O4 | — | `<E10: void monitor()>` | -1 | `<external,-1>` | **no** — `javac`'s catch-all for the `synchronized` block, exception table `12–14 → 17`, `17–20 → 17` |
| O5 | — | `<E10: void main(java.lang.String[])>` | -1 | `<external,-1>` | **no** — the `catch (Oops e)` handler, exception table `6–9 → 12` |

Named in advance so they are not mistaken for instrumentation noise: **O4 and O5 are compiler- and
source-generated caught-exception objects.** `JIdentityStmtHandler:49` marks every
`@caughtexception` local's object `Escape`. O4 is additionally rethrown by the
`monitorexit`/`athrow` epilogue, so O4 is predicted to carry **two** reasons and O5 exactly one.

So the program's honest description is **three designated single-reason objects plus two
incidental ones**, not "five single-reason objects".

## Reading A — patched (`MarkStoreEscaping=false`)

### Prediction, per object

| object | reasons | count | real | surrender | verdict |
|---|---|---:|---:|---:|---|
| O1 | `STATIC_FIELD_STORE` | 1 | 1 | 0 | `Escape` |
| O2 | `MONITOR` | 1 | 1 | 0 | `Escape` |
| O3 | `THROWN` | 1 | 1 | 0 | `Escape` |
| O4 | `CAUGHT_EXCEPTION`, `THROWN` | 2 | 2 | 0 | `Escape` |
| O5 | `CAUGHT_EXCEPTION` | 1 | 1 | 0 | `Escape` |

**Why each designated object cannot pick up a second reason.**

- **O1.** The only statements touching `a` are the `new`, the `invokespecial Item.<init>` receiver,
  and the `putstatic`. The constructor call produces a conditional value on
  `(Item.<init>, <parameter,-1>)`, and E01 already measured that `Item.<init>`'s receiver resolves
  `NoEscape` in the patched build — so the successor scan finds nothing escaping and
  `TRANSITIVE_SUCCESSOR` does not fire. `statik()` returns `void`, so there is no
  `<returnValue,0>` and no return edge.
- **O2.** Same, with `monitorenter` in place of the `putstatic`.
- **O3.** `<internal,0>` is thrown at 9. **This is the one prediction I would bet against
  myself on.** `Oops.<init>` calls `RuntimeException.<init>`, which in the JDK calls
  `fillInStackTrace()` and stores into `this`. If Stava resolves `RuntimeException.<init>`'s
  receiver to `Escape`, O3 picks up `TRANSITIVE_SUCCESSOR` as a second reason and the row above
  is wrong.
  **Alternative prediction: O3 = `{THROWN, TRANSITIVE_SUCCESSOR}`, 2 reasons.**
  If that is what comes back it is a **measurement about the JDK's exception hierarchy**, not a
  broken instrumentation, and E10's ground-truth role is carried by O1 and O2, which have no
  such exposure.

### Sets

All five objects resolve `Escape`, so **definition S gives 1 set** over this program — E10 is
another instance of F9.5 and is not a clustering example. Under the reason-set relation the same
five objects fall into **four distinct reason sets** (`{STATIC_FIELD_STORE}`, `{MONITOR}`,
`{THROWN}`, `{CAUGHT_EXCEPTION,THROWN}`, `{CAUGHT_EXCEPTION}` — five sets if O3 stays clean).
That contrast is the point of the program: the reason set separates objects that S cannot.

## Reading B — upstream (`MarkStoreEscaping=true`)

Only O1 changes. The `putstatic` at 9 has a `Local` on the right, so `StoreStmt.java:38-41`
short-circuits and O1 is stamped `STORE_CASCADE_UNTYPED` instead of `STATIC_FIELD_STORE`.

| object | patched | upstream |
|---|---|---|
| O1 | `STATIC_FIELD_STORE` | `STORE_CASCADE_UNTYPED` |
| O2 | `MONITOR` | `MONITOR` |
| O3 | `THROWN` | `THROWN` |
| O4 | `CAUGHT_EXCEPTION`, `THROWN` | `CAUGHT_EXCEPTION`, `THROWN` |
| O5 | `CAUGHT_EXCEPTION` | `CAUGHT_EXCEPTION` |

Counts are identical in both configurations — every object still has exactly one reason (two for
O4). **E10 is therefore the control**: any difference between the two configurations that shows
up on E10 is an instrumentation artefact, because the program has none by construction. E09 is
where the configurations are supposed to differ.

## What this program cannot show

- Nothing about frequency. Five objects, hand-placed.
- Nothing about the surrender constants: no object here has a missing BCI and no method is in
  `noBCIMethods`, so `isSurrender()` is exercised nowhere in this program and is untested by it.
- The `Escape`-only verdict means the figure produced from E10 alone would be one colour under
  definition S; that is expected and is not a rendering failure.
