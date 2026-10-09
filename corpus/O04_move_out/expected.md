# O04: ownership moves between an object and a frame

**Written before the run.** Tests that the borrow rule stays sound when an object leaves its
container.

## Bytecode facts

| id | site | what |
|---|---|---|
| A | `main` bci 0, `Box` | passed to `fill` at 9 and to `take` at 13 |
| B | `fill` bci 1, `Item` | stored into the Box at 8 |
| H | `main` bci 22, `Holder` | |
| P | `main` bci 31, `Item` | passed to `pass` at 38, result stored into H at 41 |

`take` loads `Box.item` at 1, stores null at 7, returns the loaded value at 11. `pass` returns
its parameter.

## Concrete ownership

B is owned by A after `fill` returns. After `take` returns, A no longer points to B, and only
main's local `t` holds it: ownership has moved from the object A to main's frame. P is held by
main's frame and by H.

## Predicted result

| site | B (v0) | N | truth |
|---|---|---|---|
| A | OWN(main) | OWN(main) | OWN(main) |
| B | UP(main), 1 up | UP(main) | UP(main) |
| H | OWN(main) | OWN(main) | OWN(main) |
| P | OWN(main) | OWN(main) | OWN(main) |

In graph B, main gets no edge for `t = take(b)`, because `take` returns a value loaded from its
parameter. The abstract path to B still runs through main: main to A by `new`, then A to B by
the `item` field, which Spark keeps because the field held B at some point. That path is why
dropping the edge is safe even after `take` has cut the concrete one.
