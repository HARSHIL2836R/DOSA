# E08 — a factory whose single allocation site serves two owners

**Written before the run.**

`PTA-Task-List` task 8 in its purest form: *"count abstract objects with more than one distinct
incoming containment source."* E08 has exactly one such object and **nothing escapes**, which is
what separates it from M02. M02 showed what merging *costs* (a false `Escape`); E08 shows the
merging itself, with the cost held at zero, so the two can be read side by side.

## Program

```java
public class E08 {
    static Box make() { return new Box(); }   // ONE allocation site, BCI 0 in make

    public static void main(String[] args) {
        Box x = make();      // invokestatic at 0, astore_1 at 3
        Box y = make();      // invokestatic at 4, astore_2 at 7
        Item i = new Item(); // BCI 8
        Item j = new Item(); // BCI 16
        x.item = i;          // putfield at 27
        y.item = j;          // putfield at 33
    }
}
class Box  { Item item; }
class Item { }
```

At run time there are two `Box` objects, `x` and `y`, each owning its own `Item`. No static
field, no return out of `main`, no call to anything unavailable.

## Abstract objects — fact (javap)

| id | method | BCI | node | what |
|---|---|---:|---|---|
| B  | `<E08: Box make()>` | 0 | `<internal,0>` | **the single `Box` allocation** |
| X1 | `<E08: void main(java.lang.String[])>` | 3 | `<external,3>` | result of `make()` — `x` |
| X2 | same | 7 | `<external,7>` | result of `make()` — `y` |
| I1 | same | 8 | `<internal,8>` | `i` |
| I2 | same | 16 | `<internal,16>` | `j` |

External BCIs 3 and 7 are the `astore` offsets, per F7.1.

## Reading A — patched (`MarkStoreEscaping=false`)

### Per-method edges — prediction

The two stores are in `main`, on the externals, so `main`'s own PTG carries them:

```
Fields:{<external,3>={<Box: Item item>=[<internal,8>]},
        <external,7>={<Box: Item item>=[<internal,16>]}}
```

| # | edge | fieldPath | provenance |
|---|---|---|---|
| e1 | X1 → I1 | `.item` | `CONTAINMENT` (store at 27) |
| e2 | X2 → I2 | `.item` | `CONTAINMENT` (store at 33) |
| e3 | B → `⟨E08.make,<returnValue,0>⟩` | `RETURN` | |
| e4 | X1 → `⟨E08.make,<returnValue,0>⟩` | `RETURN` | |
| e5 | X2 → `⟨E08.make,<returnValue,0>⟩` | `RETURN` | |
| e6 | B, I1, I2 → their constructors' `<parameter,-1>` | — | `ARGUMENT` |

**Per-method, the picture is correct and precise:** two separate containers, one `Item` each.

### After interprocedural stitching — the point of the program

Rule 1 aliases B, X1 and X2 into one node (all three name `⟨make,<returnValue,0>⟩`). The two
containment edges then both start at that one node:

```
Box@E08.make:0  --item-->  Item@E08.main:8
Box@E08.make:0  --item-->  Item@E08.main:16
```

**One abstract object, two distinct incoming containment sources — the task 8 count for E08 is
1 out of 3 merged objects.** The precision loss is visible as *fan-out from a single node* where
the program has two independent containers.

### Verdicts — prediction

Everything `NoEscape`: B, X1, X2, I1, I2. Nothing in E08 can be observed from outside `main`.

**And this is what makes E08 the control for M02.** The merging is identical in both programs;
in M02 it converted a correct `NoEscape` into a wrong `Escape` because one of the owners was
published, and here, with no publication, it costs nothing. **Allocation-site merging is not
inherently wrong — it becomes wrong when the merged objects have different fates.** That is a
sharper statement than "merging is imprecise", and it is only visible with both programs in
hand.

### Sets

**Per-method view** (5 objects, all `NoEscape`):
- **S**: **1 set.** **C**: 5 singletons — two chains ⟹ **5 sets.**

**Interprocedural view** (3 merged objects, all `NoEscape`):
- **S**: **1 set.** **C**: `{B}`, `{I1}`, `{I2}` ⟹ **3 sets.**

## Reading B — upstream (`MarkStoreEscaping=true`)

Both stores short-circuit: `cascadeEscape(i)` and `cascadeEscape(j)`.

| object | verdict | correct? |
|---|---|---|
| I1 `i`, I2 `j` | `Escape` | **no** — both false positives |
| B, X1, X2 `Box` | `NoEscape` | yes — never a store RHS |

`Fields:` empty, so no containment edges and **the merging is invisible**: the figure cannot show
fan-out from a node when there are no edges to fan out. Task 8's measurement is therefore
*unmeasurable* in the shipped configuration, which is itself worth stating.

## Prediction summary

| quantity | patched | upstream |
|---|---:|---:|
| objects (per-method) | 5 | 5 |
| merged objects (interproc) | 3 | 3 |
| alias class size for `Box` | 3 | 3 |
| containment edges (per-method / interproc) | 2 / 2 | 0 / 0 |
| `NoEscape` / `Escape` (interproc) | 3 / 0 | 1 / 2 |
| objects with >1 incoming containment source | **1** | **0 (unmeasurable)** |
| sets under S (interproc) | 1 | 2 |
| sets under C (interproc) | 3 | 3 |
