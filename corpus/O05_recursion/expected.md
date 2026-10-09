# O05: recursion

**Written before the run.**

## Bytecode facts

| id | site | what |
|---|---|---|
| T | `build` bci 0, `TreeNode` | returned; stored into `l` at 19 and `r` at 29 by the caller activation |
| C | `count` bci 6, `Counter` | scratch |

`build` calls itself at 16 and 26; `count` calls itself at 20 and 28.

## Concrete ownership

Every TreeNode is reachable, once built, only through main's local `t` and the tree's own
fields: all of them die when main returns. Each Counter is held by one activation of `count` and
dies when that activation returns.

## Predicted result

| site | B (v0) | truth |
|---|---|---|
| T | UP(main), 1 up | UP(main) |
| C | OWN(count), recursive | OWN(count), each object its own activation |

For C the analysis can only say "the oldest activation of `count` on the stack". That is sound:
every Counter dies no later than that activation returns. It is coarser than the truth, and a
frame region built on it would keep every Counter until the outermost `count` returns. Sites
whose owner method is recursive are reported separately for that reason, as the fork's walk
treats a call-graph SCC as one level.
