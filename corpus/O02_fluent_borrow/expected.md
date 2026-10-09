# O02: a method that returns its receiver

**Written before the run.** The application-class version of the `StringBuilder.append` hub
([[Micro-Corpus-Log]] F17.7, F18.4).

## Bytecode facts

| id | site | what |
|---|---|---|
| A | `local` bci 0, `Acc` | `add` called at 10 and 14, results discarded |
| B | `published` bci 0, `Acc` | `add` called at 10, result stored by `putstatic kept` at 13 |

`Acc.add` returns `this` (`areturn` at 11).

## Concrete ownership

A is reachable only from `local`'s frame and dies when `local` returns. B is reachable from the
static `kept` for the rest of the run.

## Predicted result

| site | B (v0) | with identity returns | N | truth |
|---|---|---|---|---|
| A | **HEAP** | OWN(local) | HEAP | OWN(local) |
| B | HEAP | HEAP | HEAP | HEAP |

The borrow rule removes the frame edge that `a.add(1)` would give `local`, since `add` returns a
parameter. It cannot remove the static edge. Spark gives `add`'s return node one points-to set,
{A, B}, and `kept = b.add(3)` copies that whole set into `kept`. So `kept` points to A as far as
Spark knows, and A is HEAP. This is the limit of v0 the program exists to show: a precision loss
in Spark's heap, not in the ownership rule. Rewriting `l = x.add(..)` to `x.add(..); l = x` before
Spark runs (identity returns) removes it.
