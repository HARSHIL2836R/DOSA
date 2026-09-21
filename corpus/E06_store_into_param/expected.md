# E06 — escape by store into a field of a parameter

**Written before the run.**

The complement of E02. In E02 the container reaches a static field; here the container is a
**parameter**, so the contained object's fate is conditional on the caller rather than settled
inside the method. This is the case PYE's `⟨caller, argument i⟩` conditional value exists for.

## Program

```java
public class E06 {
    static void fill(Box box) {
        Item i = new Item();   // BCI 0 in fill
        box.item = i;          // putfield at BCI 10 in fill
    }
    public static void main(String[] args) {
        Box b = new Box();     // BCI 0 in main
        fill(b);               // invokestatic at BCI 9
    }
}
class Box  { Item item; }
class Item { }
```

## Abstract objects — fact (javap)

| id | method | BCI | node | type |
|---|---|---:|---|---|
| O1 | `<E06: void main(java.lang.String[])>` | 0 | `<internal,0>` | `Box` |
| O2 | `<E06: void fill(Box)>` | 0 | `<internal,0>` | `Item` |

**Both print as `<internal,0>` and are different objects.** Object refs are method-local; only
the pair `(method, BCI)` identifies an object. This is the smallest program in the corpus that
would break any extractor keying on the ref alone, and it is deliberately included for that
reason.

Plus `fill`'s `<parameter,0>` — the `box` parameter.

## Reading A — patched (`MarkStoreEscaping=false`)

### Edges — prediction

| # | edge | fieldPath | provenance | rule |
|---|---|---|---|---|
| e1 | O1 → `⟨Box.<init>,<parameter,-1>⟩` | — | `ARGUMENT` | receiver in `main` |
| e2 | O1 → `⟨E06.fill,<parameter,0>⟩` | — | `ARGUMENT` | `fill(b)` at BCI 9 |
| e3 | O2 → `⟨Item.<init>,<parameter,-1>⟩` | — | `ARGUMENT` | receiver in `fill` |
| e4 | `fill.<parameter,0>` → O2 | `.item` | `CONTAINMENT` | the store at 10, in `fill`'s own PTG: `Fields:{<parameter,0>={<Box: Item item>=[<internal,0>]}}` |

e4 is the interesting one: **its source is a parameter node, not an object.** It only becomes an
object-to-object edge after Phase 7 rule 3 rewrites it through the binding
`fill.param0 ← {O1}`, giving `O1 --item--> O2` in the interprocedural view.

Also predicted in `fill`'s summary, from `propagateES`: O2 inherits `<parameter,0>`'s status as a
false clone, i.e. `⟨caller,<argument,0>,[F]⟩` alongside its own `⟨Item.<init>,p-1,[T]⟩`. That CV
reads *"the Item escapes if the caller's argument 0 escapes"* — exactly PYE §5.1.

### Verdicts — prediction

| object | verdict | confidence | why |
|---|---|---|---|
| O1 `Box` in `main` | `NoEscape` | high | storing **into** a parameter's field does not make the parameter escape; `b` is never published, returned or passed on |
| O2 `Item` in `fill` | `NoEscape` | medium | it is conditional on the caller's argument 0, which resolves to O1, which is `NoEscape`. The correct answer, but it requires the resolver to actually follow the `⟨caller,argument 0⟩` chain rather than give up. |

If O2 comes back `Escape`, the resolver is not resolving caller-conditional values in this
configuration, and that is a finding about the resolver worth more than E06 itself.

### Sets

**Per-method view:** two objects in two methods.
- **S**: both `{NoEscape}` ⟹ **1 set.**
- **C**: no *object-to-object* containment edge exists before stitching (e4 starts at a parameter),
  so ⟹ **2 singletons.**

**Interprocedural view:** after rule 3, `O1 --item--> O2`.
- **S**: **1 set.** **C**: **2 sets** (a chain).

## Reading B — upstream (`MarkStoreEscaping=true`)

The store at 10 short-circuits to `cascadeEscape(i)`, so O2 is `Escape` and e4 is never created.

| object | verdict |
|---|---|
| O1 `Box` | `NoEscape` — never a store RHS |
| O2 `Item` | `Escape` — **false positive**, it is only ever reachable through a `Box` that stays local |

| quantity | patched | upstream |
|---|---:|---:|
| objects | 2 | 2 |
| `NoEscape` / `Escape` | 2 / 0 | 1 / 1 |
| containment edges (per-method) | 1 | 0 |
| containment edges (interproc) | 1 | 0 |
| sets under S | 1 | 2 |
| sets under C (interproc) | 2 | 2 |

E06 is the cleanest demonstration in the corpus of `MarkStoreEscaping` turning a correct
`NoEscape` into a wrong `Escape`: the program has exactly one field store and exactly one object
whose verdict it decides.
